// SPDX-License-Identifier: GPL-3.0-or-later
/**
 * @file dcsperre.c  Gleichanteil-Sperre (DC-Blocker) für die Senderichtung (Sopho2SIP)
 *
 * Der Eingang der UCA222 liefert X_OUT der D340 mit einem Gleichanteil von etwa -49 dBFS (gemessen 2026-10-03).
 * Unhörbar, verschiebt aber die G.711-Kennlinie und stört Pegel- und Sprachpausenerkennung. Filter erster Ordnung:
 *
 *   y[n] = x[n] - x[n-1] + R * y[n-1],   R = 1 - 2*pi*fc/fs,   fc = 10 Hz
 *
 * Laden in der baresip-Konfiguration:  module  dcsperre.so   (nach dem Audiotreiber; wirkt auf ausrc → Codec)
 * Gebaut als App-Modul von baresip (tools/baresip_build.sh: APP_MODULES_DIR=gateway/baresip, APP_MODULES=dcsperre).
 */
#include <re.h>
#include <rem.h>
#include <baresip.h>

enum { MAX_KANAELE = 8 };

static const double GRENZFREQUENZ = 10.0;   /* Hz */
static const double PI = 3.14159265358979323846;


struct dcsperre_enc {
	struct aufilt_enc_st af;    /* Basisklasse, muss vorn stehen */
	double r;
	unsigned ch;
	double x1[MAX_KANAELE];
	double y1[MAX_KANAELE];
};


static void enc_destructor(void *arg)
{
	struct dcsperre_enc *st = arg;

	list_unlink(&st->af.le);
}


static int encode_update(struct aufilt_enc_st **stp, void **ctx,
			 const struct aufilt *af, struct aufilt_prm *prm,
			 const struct audio *au)
{
	struct dcsperre_enc *st;
	(void)ctx;
	(void)af;
	(void)au;

	if (!stp || !prm)
		return EINVAL;

	if (*stp)
		return 0;

	if (prm->fmt != AUFMT_S16LE) {
		warning("dcsperre: Format nicht unterstützt (%s)\n",
			aufmt_name(prm->fmt));
		return ENOTSUP;
	}

	if (!prm->srate || !prm->ch || prm->ch > MAX_KANAELE)
		return EINVAL;

	st = mem_zalloc(sizeof(*st), enc_destructor);
	if (!st)
		return ENOMEM;

	st->r  = 1.0 - 2.0 * PI * GRENZFREQUENZ / prm->srate;
	st->ch = prm->ch;

	info("dcsperre: %u Hz, %u Kanal/Kanäle, R = %.5f\n",
	     prm->srate, prm->ch, st->r);

	*stp = (struct aufilt_enc_st *)st;

	return 0;
}


static int encode_frame(struct aufilt_enc_st *stp, struct auframe *af)
{
	struct dcsperre_enc *st = (struct dcsperre_enc *)stp;
	int16_t *s;

	if (!st || !af || !af->sampv)
		return EINVAL;

	if (af->fmt != AUFMT_S16LE)
		return ENOTSUP;

	s = af->sampv;

	for (size_t i = 0; i < af->sampc; i++) {
		unsigned k = (unsigned)(i % st->ch);
		double x = s[i];
		double y = x - st->x1[k] + st->r * st->y1[k];

		st->x1[k] = x;
		st->y1[k] = y;

		if (y > 32767.0)
			y = 32767.0;
		else if (y < -32768.0)
			y = -32768.0;

		s[i] = (int16_t)(y >= 0 ? y + 0.5 : y - 0.5);
	}

	return 0;
}


static struct aufilt dcsperre = {
	.name    = "dcsperre",
	.encupdh = encode_update,
	.ench    = encode_frame,
	.decupdh = NULL,
	.dech    = NULL
};


static int module_init(void)
{
	aufilt_register(baresip_aufiltl(), &dcsperre);

	return 0;
}


static int module_close(void)
{
	aufilt_unregister(&dcsperre);

	return 0;
}


EXPORT_SYM const struct mod_export DECL_EXPORTS(dcsperre) = {
	"dcsperre",
	"filter",
	module_init,
	module_close
};
