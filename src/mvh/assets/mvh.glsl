// mvh.glsl - sample whole-song curves packed by song.textureData(ids, {layout: 'wrap'}) (mv-harness contract v1.0.0-rc.3).
//
// GLSL ES 3.00 / WebGL2 (needs texelFetch). Paste or #include it into a fragment or vertex shader; it declares no
// uniforms and no #version line. The texture is R32F (format 'r32f', NEAREST filtering, no mipmaps) or R8 ('r8', the
// sampler returns value / 255 already normalised). Channel c occupies rows [row0, row0 + rows) of a `width`-wide texture,
// sample i at texel (i % width, row0 + i / width); interpolation is done here by hand, so it is exact across row wraps
// and no MAX_TEXTURE_SIZE limit applies to the song length.
//
//   info = vec4(rate_hz, n, width, row0)  ==  textureData(...).layout[k].info
//   float v = mvhCurve(uCurves, uTime, uKickInfo);   // equals song.curve(id).at(t) (lerp; clamped at both ends)
//   float s = mvhCurveHold(uCurves, uTime, uInPulseInfo);   // 'hold' channels: nearest sample
//
// three.js: new THREE.DataTexture(td.data, td.width, td.height, THREE.RedFormat, THREE.FloatType) with
// minFilter = magFilter = THREE.NearestFilter; pass each layout entry's info as a vec4 uniform.
// The functions below are written in a small GLSL subset that tests/unit/lib/glsl.test.mjs runs as JavaScript.

int mvhDivI(int a, int b) {
  return a / b;
}

float mvhTexel(sampler2D tex, int i, vec4 info) {
  int w = int(info.z);
  int q = mvhDivI(i, w);
  int col = i - q * w;
  int row = int(info.w) + q;
  return texelFetch(tex, ivec2(col, row), 0).r;
}

float mvhCurve(sampler2D tex, float t, vec4 info) {
  float last = info.y - 1.0;
  float x = clamp(t * info.x, 0.0, last);
  float fi = floor(x);
  int i = int(fi);
  int j = min(i + 1, int(last));
  float a = mvhTexel(tex, i, info);
  float b = mvhTexel(tex, j, info);
  return a + (b - a) * (x - fi);
}

float mvhCurveHold(sampler2D tex, float t, vec4 info) {
  int last = int(info.y) - 1;
  int k = int(floor(t * info.x + 0.5));
  k = clamp(k, 0, last);
  return mvhTexel(tex, k, info);
}
