# SPDX-License-Identifier: GPL-3.0-or-later
# App-Modul für baresip: cmake -DAPP_MODULES_DIR=<repo>/gateway/baresip -DAPP_MODULES=dcsperre
project(dcsperre)

list(APPEND MODULES_DETECTED ${PROJECT_NAME})
set(MODULES_DETECTED ${MODULES_DETECTED} PARENT_SCOPE)

set(SRCS dcsperre.c)

if(STATIC)
    add_library(${PROJECT_NAME} OBJECT ${SRCS})
else()
    add_library(${PROJECT_NAME} MODULE ${SRCS})
endif()
