#include <napi.h>

#include "add.hpp"

namespace ffi_lab {
Napi::Value Add(const Napi::CallbackInfo& info) {
  const Napi::Env env = info.Env();

  if (info.Length() != 2) {
    throw Napi::TypeError::New(env, "add expects exactly 2 arguments");
  }

  if (!info[0].IsNumber() || !info[1].IsNumber()) {
    throw Napi::TypeError::New(env, "add expects two numbers");
  }

  const double a = info[0].As<Napi::Number>().DoubleValue();
  const double b = info[1].As<Napi::Number>().DoubleValue();
  const double result = ffi_lab::add(a, b);

  return Napi::Number::New(env, result);
}

Napi::Object Init(Napi::Env env, Napi::Object exports) {
  exports.Set("add", Napi::Function::New(env, Add));
  return exports;
}

NODE_API_MODULE(addon, Init)
}  // namespace ffi_lab
