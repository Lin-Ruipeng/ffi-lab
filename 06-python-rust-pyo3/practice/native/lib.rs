mod arithmetic;

use pyo3::prelude::*;

/// Add two numbers using Rust f64 arithmetic
#[pyfunction]
#[pyo3(signature = (a, b))]
fn add(a: f64, b: f64) -> f64 {
    arithmetic::add(a, b)
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(add, m)?)?;
    Ok(())
}
