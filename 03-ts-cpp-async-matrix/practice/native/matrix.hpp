#pragma once

#include <cstddef>
#include <vector>

namespace ffi_lab {

struct Matrix {
  std::size_t rows;
  std::size_t cols;
  std::vector<double> data;
};

std::size_t CheckedElementCount(std::size_t rows, std::size_t cols);
Matrix Multiply(const Matrix& a, const Matrix& b);

}  // namespace ffi_lab