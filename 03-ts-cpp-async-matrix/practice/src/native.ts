import { createRequire } from "node:module";

export type Matrix = readonly (readonly number[])[];

interface NativeAddon {
    multiplyAsync(a: Matrix, b: Matrix): Promise<number[][]>;
}

const require = createRequire(import.meta.url);
const addon = require("../../build/Release/addon.node") as NativeAddon;

export const multiplyAsync: NativeAddon["multiplyAsync"] = addon.multiplyAsync;