use napi_derive::napi;

#[napi(strict)]
pub fn add(a: f64, b: f64) -> f64 {
    a + b
}
