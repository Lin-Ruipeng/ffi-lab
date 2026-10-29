#include <pybind11/pybind11.h>

#include "add.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_core, m) {
  m.doc() = "A C++ addition function exposed with pybind11";
  m.def("add", &ffi_lab::add, py::arg("a"), py::arg("b"),
        "Add two numbers using C++ double arithmetic.");
}
