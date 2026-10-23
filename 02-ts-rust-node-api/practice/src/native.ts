type NativeAddon = typeof import("../build/index.js");

const addonUrl = new URL("../../build/index.js", import.meta.url);
const addon = (await import(addonUrl.href)) as NativeAddon;

export const add: NativeAddon["add"] = addon.add;
