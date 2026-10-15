// Render a Lucide icon as a brand badge PNG: white glyph on a #0083CA circle with a white ring.
// usage: node icon.js <lucide-name> <out.png> [size]
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const [name, out, sizeArg] = process.argv.slice(2);
const size = parseInt(sizeArg || "180", 10);
const src = fs.readFileSync(path.join(__dirname, "icons", `${name}.svg`), "utf8");
const inner = src.slice(src.indexOf(">", src.indexOf("<svg")) + 1, src.lastIndexOf("</svg>"));

const glyph = size * 0.5, off = (size - glyph) / 2, r = size / 2;
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <circle cx="${r}" cy="${r}" r="${r - 6}" fill="#0083CA" stroke="#FFFFFF" stroke-width="6"/>
  <g transform="translate(${off} ${off}) scale(${glyph / 24})" fill="none" stroke="#FFFFFF"
     stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${inner}</g>
</svg>`;
sharp(Buffer.from(svg)).png().toFile(out).then(() => console.log(out));
