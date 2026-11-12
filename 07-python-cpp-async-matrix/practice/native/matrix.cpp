#include "matrix.hpp"

#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <string>

namespace ffi_lab {
namespace {

void validate(const Matrix& matrix, const std::string& name) {
  if (matrix.empty()) {
    throw std::invalid_argument(name + " must not be empty");
  }
  const auto cols = matrix.front().size();
  if (cols == 0) {
    throw std::invalid_argument(name + " rows must not be empty");
  }
  for (const auto& row : matrix) {
    if (row.size() != cols) {
      throw std::invalid_argument(name + " rows must have equal lengths");
    }
    for (const double value : row) {
      if (!std::isfinite(value)) {
        throw std::invalid_argument(name + " elements must be finite");
      }
    }
  }
}

}  // namespace

Matrix multiply(const Matrix& a, const Matrix& b) {
  validate(a, "a");
  validate(b, "b");
  const auto rows = a.size();
  const auto shared = a.front().size();
  const auto cols = b.front().size();
  if (shared != b.size()) {
    throw std::invalid_argument("a columns must equal b rows");
  }
  if (rows > std::numeric_limits<std::size_t>::max() / cols) {
    throw std::length_error("result dimensions exceed supported size");
  }

  Matrix result(rows, std::vector<double>(cols));
  for (std::size_t row = 0; row < rows; ++row) {
    for (std::size_t col = 0; col < cols; ++col) {
      double sum = 0;
      for (std::size_t k = 0; k < shared; ++k) {
        sum += a[row][k] * b[k][col];
        if (!std::isfinite(sum)) {
          throw std::overflow_error(
              "matrix multiplication produced a non-finite value");
        }
      }
      result[row][col] = sum;
    }
  }
  return result;
}

}  // namespace ffi_lab
