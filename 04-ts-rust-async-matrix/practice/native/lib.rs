mod matrix;

use matrix::{Matrix, MatrixError, checked_element_count};
use napi::bindgen_prelude::{AsyncTask, JsObjectValue, Unknown};
use napi::{Env, Error, JsRangeError, JsTypeError, JsValue, Result, Task, ValueType};
use napi_derive::napi;

fn type_error(env: Env, message: impl Into<String>) -> Error {
    JsTypeError::from(Error::from_reason(message))
        .into_unknown(env)
        .into()
}

fn range_error(env: Env, message: impl Into<String>) -> Error {
    JsRangeError::from(Error::from_reason(message))
        .into_unknown(env)
        .into()
}

fn matrix_error(env: Env, error: MatrixError) -> Error {
    if error.is_range() {
        range_error(env, error.to_string())
    } else {
        Error::from_reason(error.to_string())
    }
}

fn read_matrix(env: Env, value: Unknown<'_>, name: &str) -> Result<Matrix> {
    if !value.is_array()? {
        return Err(type_error(env, format!("{name} must be an array of rows")));
    }
    let array = value.coerce_to_object()?;
    let rows = array.get_array_length()?;
    if rows == 0 {
        return Err(range_error(env, format!("{name} must not be empty")));
    }
    if !array.has_own_property("0")? {
        return Err(type_error(
            env,
            format!("{name} must not contain sparse rows"),
        ));
    }
    let first: Unknown = array.get_element(0)?;
    if !first.is_array()? {
        return Err(type_error(env, format!("{name} rows must be arrays")));
    }
    let cols = first.coerce_to_object()?.get_array_length()?;
    if cols == 0 {
        return Err(range_error(env, format!("{name} rows must not be empty")));
    }
    let mut matrix =
        Matrix::zeros(rows as usize, cols as usize).map_err(|error| matrix_error(env, error))?;
    for row in 0..rows {
        env.run_in_scope(|| {
            if !array.has_own_property(&row.to_string())? {
                return Err(type_error(
                    env,
                    format!("{name} must not contain sparse rows"),
                ));
            }
            let row_value: Unknown = array.get_element(row)?;
            if !row_value.is_array()? {
                return Err(type_error(env, format!("{name} rows must be arrays")));
            }
            let cells = row_value.coerce_to_object()?;
            if cells.get_array_length()? != cols {
                return Err(range_error(
                    env,
                    format!("{name} rows must have equal lengths"),
                ));
            }
            for col in 0..cols {
                if !cells.has_own_property(&col.to_string())? {
                    return Err(type_error(
                        env,
                        format!("{name} must not contain sparse elements"),
                    ));
                }
                let cell: Unknown = cells.get_element(col)?;
                if cell.get_type()? != ValueType::Number {
                    return Err(type_error(env, format!("{name} elements must be numbers")));
                }
                let number = cell.coerce_to_number()?.get_double()?;
                if !number.is_finite() {
                    return Err(range_error(env, format!("{name} elements must be finite")));
                }
                matrix.data[row as usize * matrix.cols + col as usize] = number;
            }
            Ok(())
        })?;
    }
    Ok(matrix)
}

pub struct MatrixTask {
    a: Matrix,
    b: Matrix,
    range_error: bool,
}

#[napi]
impl Task for MatrixTask {
    type Output = Matrix;
    type JsValue = Vec<Vec<f64>>;

    fn compute(&mut self) -> Result<Self::Output> {
        self.a.multiply(&self.b).map_err(|error| {
            self.range_error = error.is_range();
            Error::from_reason(error.to_string())
        })
    }

    fn resolve(&mut self, env: Env, output: Self::Output) -> Result<Self::JsValue> {
        output.into_rows().map_err(|error| matrix_error(env, error))
    }

    fn reject(&mut self, env: Env, error: Error) -> Result<Self::JsValue> {
        if self.range_error {
            Err(JsRangeError::from(error).into_unknown(env).into())
        } else {
            Err(error)
        }
    }
}

#[napi(
    ts_args_type = "a: ReadonlyArray<ReadonlyArray<number>>, b: ReadonlyArray<ReadonlyArray<number>>"
)]
pub fn multiply_async(env: Env, a: Unknown<'_>, b: Unknown<'_>) -> Result<AsyncTask<MatrixTask>> {
    let a = read_matrix(env, a, "a")?;
    let b = read_matrix(env, b, "b")?;
    if a.cols != b.rows {
        return Err(range_error(env, "a columns must equal b rows"));
    }
    checked_element_count(a.rows, b.cols).map_err(|error| matrix_error(env, error))?;
    Ok(AsyncTask::new(MatrixTask {
        a,
        b,
        range_error: false,
    }))
}
