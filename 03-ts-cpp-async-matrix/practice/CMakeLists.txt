cmake_minimum_required(VERSION 3.23)
project(ts_cpp_async_matrix LANGUAGES CXX)

add_library(addon SHARED
    native/matrix.cpp
    native/addon.cpp
    ${CMAKE_JS_SRC}
)

target_compile_features(addon PRIVATE cxx_std_17)
target_compile_definitions(addon PRIVATE
    NAPI_VERSION=8
    NODE_ADDON_API_CPP_EXCEPTIONS
)
target_include_directories(addon PRIVATE ${CMAKE_JS_INC})
target_link_libraries(addon PRIVATE ${CMAKE_JS_LIB})

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(addon PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

set_target_properties(addon PROPERTIES
    PREFIX ""
    SUFFIX ".node"
    CXX_EXTENSIONS OFF
)
