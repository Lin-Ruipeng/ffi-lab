import { performance } from "node:perf_hooks";

import { multiplyAsync } from "./native.js";

const rows = 600;
const shared = 800;
const cols = 500;
const a = Array.from({ length: rows }, () => Array<number>(shared).fill(1));
const b = Array.from({ length: shared }, () => Array<number>(cols).fill(1));

let beats = 0;
const timer = setInterval(() => {
    console.log(`heartbeat ${++beats}`);
}, 50);

try {
    const started = performance.now();
    const pending = multiplyAsync(a, b);
    console.log(`queued ${rows}x${shared} * ${shared}x${cols}; waiting with await`);
    const result = await pending;
    console.log(`result: ${result.length}x${result[0].length}; first = ${result[0][0]}`);
    console.log(`heartbeats: ${beats}; elapsed: ${(performance.now() - started).toFixed(1)} ms`);
} finally {
    clearInterval(timer);
}
