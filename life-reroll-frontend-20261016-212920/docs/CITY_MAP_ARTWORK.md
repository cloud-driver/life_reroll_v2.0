# City panorama and route preservation

Generated extension: `public/life-reroll-city-panorama.png` (2120 × 742).
Protected original: `public/life-reroll-city.png` (1672 × 941).
Renderer: `components/city-map-artwork.tsx`.

The built-in image generation tool produced the peripheral panorama. The original map is retained as the foreground layer at its original world coordinates. Only its outermost horizontal 4.8% blends into the new scenery. Every existing vehicle route, including the entire car sprite, stays inside the fully opaque protected area. Neither `lib/map-data.ts` nor `lib/travel.ts` is changed.

District names are real SVG text, not raster lettering: 生活區（家）, 工作區, 金融區, 休閒區. They scale with the map and adjust their font size for small windows.

The illustration and vehicle SVG share one camera. At 16:9 the original center is visible; wider banners reveal the left and right extensions. Beyond the panorama's native ratio, or in portrait windows, the whole map is uniformly fitted rather than stretched or cropped. The core map is always centered and fully visible. The city demonstration also uses the same district artwork.

Validation: `node tests/banner-map-check.mjs`, `node tests/viewport-check.mjs`, `node tests/travel-check.mjs`.

## Final generation prompt (built-in imagegen)

Use case: precise-object-edit / outpainting. Asset type: ultra-wide horizontal game city map background, panoramic 32:9 composition. Edit target: attached original Life Reroll isometric city map. Primary request: EXTEND THE MAP HORIZONTALLY ONLY, adding matching illustrated scenery to the left and right, while keeping the entire original 1672x941 composition centered, at its original scale, occupying exactly the central 50 percent of the new 3344x941 canvas. The original central rectangle must be unchanged: same center house and fence, same roads, every intersection, lane markings, bridges, river, finance district upper left, hospital lower left, office district lower right, leisure district upper right. Do not redraw, move, reshape, widen, straighten, or add obstacles to ANY existing street. Do not move buildings or camera angle. Outpaint only the new left and right outer quarters with seamless continuation of existing neighborhoods, leafy parks, background buildings, river embankments, and existing road continuations. Match the existing polished hand-painted anime isometric city illustration: ivory buildings, blue glass, sage greenery, pastel blue river, warm daylight, clean delicate linework. New outer edges should be calm peripheral scenery, not new destination landmarks. No labels, no text, no UI, no cars or people; labels and moving vehicles are added separately by the application. Full-bleed panorama, no borders, no blank gaps. Preserve the original center geometry; this is essential for existing vehicle coordinates.
