// Rasterise the site mark into the icon files browsers ask for by convention.
//
// We shipped only favicon.svg at first, which every current browser honours.
// The access log disagreed: /favicon.ico, /apple-touch-icon.png and
// /apple-touch-icon-precomposed.png were 404ing for real readers on 18
// different networks — iOS asks for the touch icons when someone shares a link
// or adds the site to their home screen, and asks for neither SVG nor manifest
// first. A blank square on a voter's home screen is a silly way to lose them.
//
// Run: node scripts/make-icons.mjs   (writes into public/)
import sharp from "sharp";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const TEAL = "#146b6b";

// Two geometries from the same mark. The favicon keeps the rounded corners,
// because it sits on a browser tab against an unknown background. The Apple
// touch icon is full-bleed square: iOS applies its own corner mask, so our own
// rounding would be clipped twice and the checkmark would sit too small.
const mark = (rx, inset) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="${rx}" fill="${TEAL}"/>
  <path d="M${inset} 19.5l5 5 11-13" fill="none" stroke="#fff" stroke-width="3.4"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;

const png = (svg, size) =>
  sharp(Buffer.from(svg), { density: 384 }).resize(size, size).png({ compressionLevel: 9 }).toBuffer();

// ICO is a container; since Vista it may hold PNGs verbatim, so we embed ours
// rather than writing BMP planes.
function ico(images) {
  const dir = Buffer.alloc(6);
  dir.writeUInt16LE(0, 0);             // reserved
  dir.writeUInt16LE(1, 2);             // type: icon
  dir.writeUInt16LE(images.length, 4);
  let offset = 6 + images.length * 16;
  const entries = images.map(({ size, data }) => {
    const e = Buffer.alloc(16);
    e.writeUInt8(size === 256 ? 0 : size, 0); // 0 means 256
    e.writeUInt8(size === 256 ? 0 : size, 1);
    e.writeUInt8(0, 2);                       // palette colours
    e.writeUInt8(0, 3);                       // reserved
    e.writeUInt16LE(1, 4);                    // colour planes
    e.writeUInt16LE(32, 6);                   // bits per pixel
    e.writeUInt32LE(data.length, 8);
    e.writeUInt32LE(offset, 12);
    offset += data.length;
    return e;
  });
  return Buffer.concat([dir, ...entries, ...images.map((i) => i.data)]);
}

const favicon = mark(7, 8);
const touch = mark(0, 7);

const sizes = [16, 32, 48];
const images = [];
for (const size of sizes) images.push({ size, data: await png(favicon, size) });
await writeFile(join(PUBLIC, "favicon.ico"), ico(images));

// 180px is what current iOS wants; the -precomposed name is what older iOS
// asks for first, and it was 404ing twelve times, so write both.
const touch180 = await png(touch, 180);
await writeFile(join(PUBLIC, "apple-touch-icon.png"), touch180);
await writeFile(join(PUBLIC, "apple-touch-icon-precomposed.png"), touch180);

console.log(`favicon.ico                       ${sizes.join("/")}px  ${images.reduce((n, i) => n + i.data.length, 0)} B`);
console.log(`apple-touch-icon.png              180px  ${touch180.length} B`);
console.log(`apple-touch-icon-precomposed.png  180px  ${touch180.length} B`);
