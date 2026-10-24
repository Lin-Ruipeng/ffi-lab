#include <napi.h>

#include <cmath>
#include <cstdint>
#include <exception>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

#include "matrix.hpp"

namespace {

ffi_lab::Matrix ReadMatrix(Napi::Env env, Napi::Value value,
                           const std::string& name) {
  if (!value.IsArray()) {
    throw Napi::TypeError::New(env, name + " must be an array of rows");
  }
  const auto array = value.As<Napi::Array>();
  const std::uint32_t rows = array.Length();
  if (rows == 0) {
    throw Napi::RangeError::New(env, name + " must not be empty");
  }

  ffi_lab::Matrix matrix{rows, 0, {}};
  for (std::uint32_t row = 0; row < rows; ++row) {
    Napi::HandleScope scope(env);
    if (!array.HasOwnProperty(std::to_string(row))) {
      throw Napi::TypeError::New(env, name + " must not contain sparse rows");
    }
    const Napi::Value row_value = array.Get(row);
    if (!row_value.IsArray()) {
      throw Napi::TypeError::New(env, name + " rows must be arrays");
    }
    const auto cells = row_value.As<Napi::Array>();
    if (row == 0) {
      matrix.cols = cells.Length();
      if (matrix.cols == 0) {
        throw Napi::RangeError::New(env, name + " rows must not be empty");
      }
      matrix.data.resize(
          ffi_lab::CheckedElementCount(matrix.rows, matrix.cols));
    } else if (cells.Length() != matrix.cols) {
      throw Napi::RangeError::New(env, name + " rows must have equal lengths");
    }

    for (std::uint32_t col = 0; col < matrix.cols; ++col) {
      if (!cells.HasOwnProperty(std::to_string(col))) {
        throw Napi::TypeError::New(env,
                                   name + " must not contain sparse elements");
      }
      const Napi::Value cell = cells.Get(col);
      if (!cell.IsNumber()) {
        throw Napi::TypeError::New(env, name + " elements must be numbers");
      }
      const double number = cell.As<Napi::Number>().DoubleValue();
      if (!std::isfinite(number)) {
        throw Napi::RangeError::New(env, name + " elements must be finite");
      }
      matrix.data[row * matrix.cols + col] = number;
    }
  }
  return matrix;
}

Napi::Array WriteMatrix(Napi::Env env, const ffi_lab::Matrix& matrix) {
  auto array = Napi::Array::New(env, matrix.rows);
  for (std::uint32_t row = 0; row < matrix.rows; ++row) {
    Napi::HandleScope scope(env);
    auto cells = Napi::Array::New(env, matrix.cols);
    for (std::uint32_t col = 0; col < matrix.cols; ++col) {
      cells.Set(col,
                Napi::Number::New(env, matrix.data[row * matrix.cols + col]));
    }
    array.Set(row, cells);
  }
  return array;
}

class MatrixWorker final : public Napi::AsyncWorker {
 public:
  MatrixWorker(Napi::Env env, Napi::Promise::Deferred deferred,
               ffi_lab::Matrix a, ffi_lab::Matrix b)
      : Napi::AsyncWorker(env, "ffi-lab:matrix-multiply"),
        deferred_(deferred),
        a_(std::move(a)),
        b_(std::move(b)) {}

  void Execute() override {
    try {
      result_ = ffi_lab::Multiply(a_, b_);
    } catch (const std::overflow_error& error) {
      range_error_ = true;
      SetError(error.what());
    }
  }

  void OnOK() override {
    try {
      deferred_.Resolve(WriteMatrix(Env(), result_));
    } catch (const Napi::Error& error) {
      deferred_.Reject(error.Value());
    } catch (const std::exception& error) {
      deferred_.Reject(Napi::Error::New(Env(), error.what()).Value());
    }
  }

  void OnError(const Napi::Error& error) override {
    if (range_error_) {
      deferred_.Reject(Napi::RangeError::New(Env(), error.Message()).Value());
    } else {
      deferred_.Reject(error.Value());
    }
  }

 private:
  Napi::Promise::Deferred deferred_;
  ffi_lab::Matrix a_;
  ffi_lab::Matrix b_;
  ffi_lab::Matrix result_{};
  bool range_error_ = false;
};

Napi::Value MultiplyAsync(const Napi::CallbackInfo& info) {
  const Napi::Env env = info.Env();
  const auto deferred = Napi::Promise::Deferred::New(env);
  try {
    if (info.Length() != 2) {
      throw Napi::TypeError::New(env,
                                 "multiplyAsync expects exactly 2 arguments");
    }
    auto a = ReadMatrix(env, info[0], "a");
    auto b = ReadMatrix(env, info[1], "b");
    if (a.cols != b.rows) {
      throw Napi::RangeError::New(env, "a columns must equal b rows");
    }
    ffi_lab::CheckedElementCount(a.rows, b.cols);
    auto worker = std::make_unique<MatrixWorker>(env, deferred, std::move(a),
                                                 std::move(b));
    worker->Queue();
    worker.release();
  } catch (const Napi::Error& error) {
    deferred.Reject(error.Value());
  } catch (const std::length_error& error) {
    deferred.Reject(Napi::RangeError::New(env, error.what()).Value());
  } catch (const std::exception& error) {
    deferred.Reject(Napi::Error::New(env, error.what()).Value());
  }
  return deferred.Promise();
}

Napi::Object Init(Napi::Env env, Napi::Object exports) {
  exports.Set("multiplyAsync", Napi::Function::New(env, MultiplyAsync));
  return exports;
}

}  // namespace

NODE_API_MODULE(addon, Init)
