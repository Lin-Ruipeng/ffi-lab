type NativeAddon = typeof import("../build/index.js")

const addonUrl = new URL("../../build/index.js", import.meta.url);
const addon = (await import(addonUrl.href)) as NativeAddon;

export type Matrix = readonly (readonly number[])[];

export async function multiplyAsync(a: Matrix, b: Matrix): Promise<number[][]> {
    if (arguments.length !== 2) {
        throw new TypeError("multiplyAsync expects exactly 2 arguments");
    }
    return addon.multiplyAsync(a, b);
}
