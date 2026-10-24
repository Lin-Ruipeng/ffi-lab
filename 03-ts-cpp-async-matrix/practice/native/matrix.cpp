#include "matrix.hpp"

#include <cmath>
#include <limits>
#include <stdexcept>

namespace ffi_lab {

std::size_t CheckedElementCount(std::size_t rows, std::size_t cols) {
  if (rows == 0 || cols == 0) {
    throw std::invalid_argument("matrix dimensions must be positive");
  }
  if (rows > std::numeric_limits<std::size_t>::max() / cols ||
      rows * cols > std::vector<double>().max_size()) {
    throw std::length_error("matrix dimensions exceed supported size");
  }
  return rows * cols;
}

Matrix Multiply(const Matrix& a, const Matrix& b) {
  if (a.cols != b.rows) {
    throw std::invalid_argument("a columns must equal b rows");
  }
  if (a.data.size() != CheckedElementCount(a.rows, a.cols) ||
      b.data.size() != CheckedElementCount(b.rows, b.cols)) {
    throw std::invalid_argument("matrix storage does not match its shape");
  }

  Matrix result{a.rows, b.cols,
                std::vector<double>(CheckedElementCount(a.rows, b.cols))};
  for (std::size_t row = 0; row < a.rows; ++row) {
    for (std::size_t col = 0; col < b.cols; ++col) {
      double sum = 0;
      for (std::size_t k = 0; k < a.cols; ++k) {
        sum += a.data[row * a.cols + k] * b.data[k * b.cols + col];
        if (!std::isfinite(sum)) {
          throw std::overflow_error(
              "matrix multiplication produced a non-finite value");
        }
      }
      result.data[row * result.cols + col] = sum;
    }
  }
  return result;
}

}  // namespace ffi_lab