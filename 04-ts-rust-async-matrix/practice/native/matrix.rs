use std::fmt;
use std::mem::size_of;

#[derive(Debug)]
pub enum MatrixError {
    Range(String),
    Allocation(String),
}

impl MatrixError {
    pub fn is_range(&self) -> bool {
        matches!(self, Self::Range(_))
    }
}

impl fmt::Display for MatrixError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Range(message) | Self::Allocation(message) => formatter.write_str(message),
        }
    }
}

pub type MatrixResult<T> = Result<T, MatrixError>;

pub struct Matrix {
    pub rows: usize,
    pub cols: usize,
    pub data: Vec<f64>,
}

pub fn checked_element_count(rows: usize, cols: usize) -> MatrixResult<usize> {
    if rows == 0 || cols == 0 {
        return Err(MatrixError::Range(
            "matrix dimensions must be positive".into(),
        ));
    }
    let count = rows
        .checked_mul(cols)
        .filter(|count| *count <= (isize::MAX as usize) / size_of::<f64>())
        .ok_or_else(|| MatrixError::Range("matrix dimensions exceed supported size".into()))?;
    Ok(count)
}

impl Matrix {
    pub fn zeros(rows: usize, cols: usize) -> MatrixResult<Self> {
        let count = checked_element_count(rows, cols)?;
        let mut data = Vec::new();
        data.try_reserve_exact(count).map_err(|error| {
            MatrixError::Allocation(format!("matrix allocation failed: {error}"))
        })?;
        data.resize(count, 0.0);
        Ok(Self { rows, cols, data })
    }

    fn validate_storage(&self) -> MatrixResult<()> {
        if self.data.len() != checked_element_count(self.rows, self.cols)? {
            return Err(MatrixError::Range(
                "matrix storage does not match its shape".into(),
            ));
        }
        Ok(())
    }

    pub fn multiply(&self, other: &Self) -> MatrixResult<Self> {
        self.validate_storage()?;
        other.validate_storage()?;
        if self.cols != other.rows {
            return Err(MatrixError::Range("a columns must equal b rows".into()));
        }
        let mut result = Self::zeros(self.rows, other.cols)?;
        for row in 0..self.rows {
            for col in 0..other.cols {
                let mut sum = 0.0;
                for k in 0..self.cols {
                    sum += self.data[row * self.cols + k] * other.data[k * other.cols + col];
                    if !sum.is_finite() {
                        return Err(MatrixError::Range(
                            "matrix multiplication produced a non-finite value".into(),
                        ));
                    }
                }
                result.data[row * result.cols + col] = sum;
            }
        }
        Ok(result)
    }

    pub fn into_rows(self) -> MatrixResult<Vec<Vec<f64>>> {
        self.validate_storage()?;
        let allocation_error =
            |error| MatrixError::Allocation(format!("result allocation failed: {error}"));
        let mut rows = Vec::new();
        rows.try_reserve_exact(self.rows)
            .map_err(allocation_error)?;
        for chunk in self.data.chunks(self.cols) {
            let mut row = Vec::new();
            row.try_reserve_exact(self.cols).map_err(allocation_error)?;
            row.extend_from_slice(chunk);
            rows.push(row);
        }
        Ok(rows)
    }
}
