import assert from "node:assert/strict";
import { test } from "node:test";

import { add } from "../src/native.js";

test("adds positive numbers", () => {
    assert.equal(add(2, 3), 5);
});

test("adds negative numbers", () => {
    assert.equal(add(-2, -3), -5);
    assert.equal(add(-2, 3), 1);
});

test("adds zero", () => {
    assert.equal(add(0, 0), 0);
    assert.equal(add(0, 7), 7);
});

test("adds decimals using floating-point arithmetic", () => {
    assert.equal(add(1.5, 2.25), 3.75);
    assert.ok(Math.abs(add(0.1, 0.2) - 0.3) < 1e-12);
});

test("preserves number semantics for NaN and Infinity", () => {
    assert.ok(Number.isNaN(add(Number.NaN, 1)));
    assert.equal(add(Number.POSITIVE_INFINITY, 1), Number.POSITIVE_INFINITY);
    assert.ok(Number.isNaN(add(Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY)));
});

test("rejects non-number arguments in either position", () => {
    const invalidValues: unknown[] = ["2", undefined, null, true, {}, 2n];

    for (const value of invalidValues) {
        assert.throws(
            () => Reflect.apply(add, undefined, [value, 3]),
            {
                code: "InvalidArg",
            }
        );
        assert.throws(
            () => Reflect.apply(add, undefined, [2, value]),
            {
                code: "InvalidArg",
            }
        );

    }
});

test("rejects missing arguments", () => {
    for (const args of [[], [2]]) {
        assert.throws(() => Reflect.apply(add, undefined, args), {
            code: "InvalidArg",
        });
    }
});

test("ignores extra arguments at the native boundary", () => {
    assert.equal(Reflect.apply(add, undefined, [2, 3, 4]), 5);
});
