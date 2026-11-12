#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "matrix.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_core, m) {
  m.doc() = "C++ matrix multiplication with the GIL released";
  m.def(
      "multiply", &ffi_lab::multiply, py::arg("a"), py::arg("b"),
      py::call_guard<py::gil_scoped_release>(),
      "Multiply two finite rectangular matrices using C++ double arithmetic.");
}
