// Bundle budget and leak check for the production build (run after `npm run build`; CI does).
//
// 1. What the first page load needs (the entry script plus everything index.html preloads) must
//    stay under INITIAL_BUDGET_KB gzipped: it is what a responder downloads on a phone at 3 a.m.
// 2. No single lazy chunk may exceed CHUNK_BUDGET_KB gzipped.
// 3. Nothing environment-specific or secret may be baked into the bundle: dev server addresses,
//    private keys, cloud credentials, Django secrets.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const INITIAL_BUDGET_KB = 170;
const CHUNK_BUDGET_KB = 130;
const dist = new URL("../dist/", import.meta.url).pathname;
const html = readFileSync(join(dist, "index.html"), "utf8");
const gz = (file) => gzipSync(readFileSync(join(dist, file))).length / 1024;

const initial = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.js)"/g)].map((m) => m[1]);
const initialKb = initial.reduce((sum, f) => sum + gz(f), 0);
const failures = [];
console.log(
  `initial JS: ${initial.length} file(s), ${initialKb.toFixed(1)} kB gzip (budget ${INITIAL_BUDGET_KB})`,
);
if (initialKb > INITIAL_BUDGET_KB)
  failures.push(`initial JS ${initialKb.toFixed(1)} kB > ${INITIAL_BUDGET_KB} kB`);

const assets = readdirSync(join(dist, "assets"));
for (const file of assets.filter((f) => f.endsWith(".js"))) {
  const kb = gz(join("assets", file));
  if (kb > CHUNK_BUDGET_KB)
    failures.push(`${file} is ${kb.toFixed(1)} kB gzip > ${CHUNK_BUDGET_KB} kB`);
}

const FORBIDDEN = [
  [/https?:\/\/(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d+/, "a dev-server address"],
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----/, "a private key"],
  [/\bAKIA[0-9A-Z]{16}\b/, "an AWS access key id"],
  [/\bsk_(?:live|test)_[0-9a-zA-Z]{10,}/, "a Stripe-style secret key"],
  [/dev-only-insecure-key|SECRET_KEY\s*[:=]/, "a Django SECRET_KEY"],
  [/\bAC[0-9a-f]{32}\b/, "a Twilio account SID"],
];
for (const file of [...assets.map((f) => join("assets", f)), "index.html"]) {
  const text = readFileSync(join(dist, file), "utf8");
  for (const [pattern, what] of FORBIDDEN) {
    const hit = text.match(pattern);
    if (hit) failures.push(`${file} contains ${what}: ${hit[0].slice(0, 40)}`);
  }
}

if (failures.length) {
  console.error("bundle check FAILED:\n  " + failures.join("\n  "));
  process.exit(1);
}
console.log(`bundle check ok: ${assets.length} assets, no budget breach, nothing leaked`);
