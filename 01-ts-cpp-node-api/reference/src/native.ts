import { createRequire } from "node:module";

interface NativeAddon {
  add(a: number, b: number): number;
}

const require = createRequire(import.meta.url);
const addon = require("../../build/Release/addon.node") as NativeAddon;

export const add: NativeAddon["add"] = addon.add;
