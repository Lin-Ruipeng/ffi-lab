import { createRequire } from "node:module";

interface NativateAddon {
    add(a: number, b: number): number;
}

const require = createRequire(import.meta.url);
const addon = require("../../build/Release/addon.node") as NativateAddon;

export const add: NativateAddon["add"] = addon.add;
