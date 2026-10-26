import { multiplyAsync } from "./native.js";

const a = [[1, 2, 3], [4, 5, 6]];
const b = [[7, 8], [9, 10], [11, 12]];

const pending = multiplyAsync(a, b);
console.log("submitted; JavaScript continues before await");
console.log("2x3 * 3x2 =", JSON.stringify(await pending));

const products = await Promise.all([
    multiplyAsync([[2]], [[3]]),
    multiplyAsync([[1, 2, 3]], [[4], [5], [6]]),
])
console.log("Promise.all =", JSON.stringify(products));

try {
    await multiplyAsync([[1, 2]], [[3, 4]]);
} catch (error) {
    if (!(error instanceof Error)) throw error;
    console.log("caught:", error.name, error.message);
}
