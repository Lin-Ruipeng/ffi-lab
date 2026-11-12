#pragma once

#include <vector>

namespace ffi_lab {

using Matrix = std::vector<std::vector<double>>;

Matrix multiply(const Matrix& a, const Matrix& b);

}  // namespace ffi_lab
