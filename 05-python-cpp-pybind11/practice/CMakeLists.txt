cmake_minimum_required(VERSION 3.18...4.2)
project(py_cpp_pybind11_add LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_core native/add.cpp native/bindings.cpp)
target_compile_features(_core PRIVATE cxx_std_17)
set_target_properties(_core PROPERTIES CXX_EXTENSIONS OFF)

if(MSVC)
    target_compile_options(_core PRIVATE /W4 /WX)
else()
    target_compile_options(_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

install(TARGETS _core LIBRARY DESTINATION cpp_add RUNTIME DESTINATION cpp_add)
