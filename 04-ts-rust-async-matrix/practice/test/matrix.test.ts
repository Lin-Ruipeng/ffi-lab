import assert from "node:assert/strict";
import { createHook } from "node:async_hooks";
import { test } from "node:test";

import { multiplyAsync, type Matrix } from "../src/native.js";

function referenceMultiply(a: Matrix, b: Matrix): number[][] {
    return a.map((row) => b[0].map((_, col) =>
        row.reduce((sum, value, k) => sum + value * b[k][col], 0),
    ));
}

async function rejectsArguments(
    args: unknown[],
    name: string,
    message?: string,
): Promise<void> {
    const pending: unknown = Reflect.apply(multiplyAsync, undefined, args);
    assert.ok(pending instanceof Promise);
    await assert.rejects(pending, message === undefined ? { name } : { name, message });
}

test("returns a Promise and settles after the caller continues", async () => {
    const events: string[] = [];
    const pending = multiplyAsync([[2]], [[3]]).then((result) => {
        events.push("resolved");
        return result;
    });
    assert.ok(pending instanceof Promise);
    events.push("returned");
    assert.deepEqual(events, ["returned"]);
    assert.deepEqual(await pending, [[6]]);
    assert.deepEqual(events, ["returned", "resolved"]);
});

test("multiplies a 2x3 matrix by a 3x2 matrix", async () => {
    assert.deepEqual(
        await multiplyAsync([[1, 2, 3], [4, 5, 6]], [[7, 8], [9, 10], [11, 12]]),
        [[58, 64], [139, 154]],
    );
});

test("supports different rectangular shapes and single elements", async () => {
    const cases: [Matrix, Matrix][] = [
        [[[3]], [[4]]],
        [[[1, 2, 3, 4]], [[2], [3], [4], [5]]],
        [[[2], [3], [4]], [[5, 6, 7, 8]]],
        [[[1, 2], [3, 4], [5, 6]], [[7, 8, 9], [10, 11, 12]]],
    ];
    for (const [a, b] of cases) {
        assert.deepEqual(await multiplyAsync(a, b), referenceMultiply(a, b));
    }
});

test("multiplies by identity matrices on either side", async () => {
    const matrix = [[1, 2, 3], [4, 5, 6]];
    assert.deepEqual(await multiplyAsync([[1, 0], [0, 1]], matrix), matrix);
    assert.deepEqual(
        await multiplyAsync(matrix, [[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
        matrix,
    );
});

test("handles zero matrices", async () => {
    assert.deepEqual(await multiplyAsync([[0, 0], [0, 0]], [[1], [2]]), [[0], [0]]);
    assert.deepEqual(await multiplyAsync([[1, 2]], [[0, 0], [0, 0]]), [[0, 0]]);
});

test("handles negative numbers", async () => {
    const a = [[-1, 2], [3, -4]];
    const b = [[5, -6], [-7, 8]];
    assert.deepEqual(await multiplyAsync(a, b), referenceMultiply(a, b));
});

test("handles decimals with a floating-point tolerance", async () => {
    const a = [[0.1, 0.2], [1.5, -2.25]];
    const b = [[0.3, 2.5], [0.4, -1.5]];
    const actual = await multiplyAsync(a, b);
    const expected = referenceMultiply(a, b);
    actual.forEach((row, i) => row.forEach((value, j) => {
        assert.ok(Math.abs(value - expected[i][j]) < 1e-12);
    }));
});

test("accepts readonly frozen matrices", async () => {
    const a = Object.freeze([Object.freeze([1, 2])]);
    const b = Object.freeze([Object.freeze([3]), Object.freeze([4])]);
    assert.deepEqual(await multiplyAsync(a, b), [[11]]);
});

test("does not modify input matrices", async () => {
    const a = [[1, 2], [3, 4]];
    const b = [[5], [6]];
    const before = structuredClone([a, b]);
    await multiplyAsync(a, b);
    assert.deepEqual([a, b], before);
});

test("uses input snapshots taken before returning the Promise", async () => {
    const a = [[1, 2], [3, 4]];
    const b = [[5], [6]];
    const pending = multiplyAsync(a, b);
    a[0][0] = 999;
    a.push([999, 999]);
    b[0][0] = -999;
    b[1] = [999];
    assert.deepEqual(await pending, [[17], [39]]);
});

test("returns independent output rows", async () => {
    const result = await multiplyAsync([[1], [2]], [[3, 4]]);
    assert.notEqual(result[0], result[1]);
    result[0][0] = 999;
    assert.deepEqual(result[1], [6, 8]);
});

test("keeps Promise.all jobs independent and preserves input ordering", async () => {
    const jobs: [Matrix, Matrix][] = [
        [[[1, 2]], [[3], [4]]],
        [[[5]], [[6, 7, 8]]],
        [[[1], [2], [3]], [[4, 5]]],
    ];
    const results = await Promise.all(jobs.map(([a, b]) => multiplyAsync(a, b)));
    assert.deepEqual(results, jobs.map(([a, b]) => referenceMultiply(a, b)));
});

test("rejects missing or extra arguments through a Promise", async () => {
    for (const args of [[], [[[1]]], [[[1]], [[2]], [[3]]]]) {
        await rejectsArguments(args, "TypeError", "multiplyAsync expects exactly 2 arguments");
    }
});

test("rejects non-array matrices in either position", async () => {
    const invalid: unknown[] = [undefined, null, 1, "1", true, {}, 1n, new Float64Array([1])];
    for (const value of invalid) {
        await rejectsArguments([value, [[1]]], "TypeError");
        await rejectsArguments([[[1]], value], "TypeError");
    }
});

test("rejects non-array rows in either position", async () => {
    for (const value of [1, "1", null, {}, new Float64Array([1])]) {
        await rejectsArguments([[value], [[1]]], "TypeError");
        await rejectsArguments([[[1]], [value]], "TypeError");
    }
});

test("rejects non-number elements in either position", async () => {
    const invalid: unknown[] = ["1", undefined, null, true, {}, 1n];
    for (const value of invalid) {
        await rejectsArguments([[[value]], [[1]]], "TypeError");
        await rejectsArguments([[[1]], [[value]]], "TypeError");
    }
});

test("rejects sparse outer arrays and sparse rows", async () => {
    const sparseOuter = new Array<unknown>(1);
    const sparseCells = [new Array<unknown>(1)];
    for (const value of [sparseOuter, sparseCells]) {
        await rejectsArguments([value, [[1]]], "TypeError");
        await rejectsArguments([[[1]], value], "TypeError");
    }
});

test("rejects empty matrices and empty rows", async () => {
    for (const value of [[], [[]], [[], []]]) {
        await rejectsArguments([value, [[1]]], "RangeError");
        await rejectsArguments([[[1]], value], "RangeError");
    }
});

test("rejects ragged matrices", async () => {
    for (const value of [[[1, 2], [3]], [[1], []]]) {
        await rejectsArguments([value, [[1]]], "RangeError");
        await rejectsArguments([[[1]], value], "RangeError");
    }
});

test("rejects incompatible multiplication dimensions", async () => {
    await rejectsArguments([[[1, 2]], [[3, 4]]], "RangeError", "a columns must equal b rows");
});

test("rejects NaN and Infinity inputs", async () => {
    for (const value of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
        await rejectsArguments([[[value]], [[1]]], "RangeError");
        await rejectsArguments([[[1]], [[value]]], "RangeError");
    }
});

test("rejects overflow detected in background computation", async () => {
    await assert.rejects(multiplyAsync([[Number.MAX_VALUE]], [[2]]), {
        name: "RangeError",
        message: "matrix multiplication produced a non-finite value",
    });
    await assert.rejects(multiplyAsync([[Number.MAX_VALUE, Number.MAX_VALUE]], [[1], [1]]), {
        name: "RangeError",
    });
});

test("creates and completes the AsyncTask native async resource", async () => {
    type Binding = typeof import("../build/index.js");
    const bindingUrl = new URL("../../build/index.js", import.meta.url);
    const binding = (await import(bindingUrl.href)) as Binding;
    const records: { id: number; type: string; resource: object }[] = [];
    const callbacks = new Set<number>();
    const hook = createHook({
        init(id, type, _trigger, resource) {
            records.push({ id, type, resource });
        },
        before(id) {
            callbacks.add(id);
        },
    });
    hook.enable();
    try {
        const pending = binding.multiplyAsync([[2]], [[4]]);
        assert.ok(pending instanceof Promise);
        const work = records.filter(({ type, resource }) =>
            type !== "PROMISE" && resource === pending,
        );
        assert.equal(work.length, 1);
        assert.deepEqual(await pending, [[8]]);
        assert.ok(callbacks.has(work[0].id));
    } finally {
        hook.disable();
    }
});

test("rejects an input getter exception without throwing synchronously", async () => {
    const failure = new Error("input getter failed");
    const a = [[1]];
    Object.defineProperty(a[0], "0", { get() { throw failure; } });
    const pending = multiplyAsync(a, [[1]]);
    assert.ok(pending instanceof Promise);
    await assert.rejects(pending, (error) => error === failure);
});

test("a failing job does not corrupt another queued job", async () => {
    const results = await Promise.allSettled([
        multiplyAsync([[Number.MAX_VALUE]], [[2]]),
        multiplyAsync([[3]], [[7]]),
    ]);
    assert.equal(results[0].status, "rejected");
    assert.deepEqual(results[1], { status: "fulfilled", value: [[21]] });
});
