// CRT / scanline post-process shader — Doom/Duke Nukem retro feel.
// Apply to a full-screen ColorRect with the screen texture.
shader_type canvas_item;

uniform float scanline_strength : hint_range(0.0, 1.0) = 0.15;
uniform float vignette_strength : hint_range(0.0, 1.0) = 0.3;
uniform float chromatic_aberration : hint_range(0.0, 5.0) = 0.8;
uniform float curvature : hint_range(0.0, 0.1) = 0.02;
uniform float flicker_speed : hint_range(0.0, 10.0) = 2.0;
uniform float flicker_strength : hint_range(0.0, 0.1) = 0.015;
uniform sampler2D SCREEN_TEXTURE : hint_screen_texture, filter_nearest;

vec2 curve_uv(vec2 uv) {
	uv = uv * 2.0 - 1.0;
	vec2 offset = abs(uv.yx) * curvature;
	uv = uv + uv * offset * offset;
	uv = uv * 0.5 + 0.5;
	return uv;
}

void fragment() {
	vec2 uv = curve_uv(SCREEN_UV);

	// Discard pixels outside curved screen
	if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
		COLOR = vec4(0.0, 0.0, 0.0, 1.0);
		return;
	}

	// Chromatic aberration
	float ca = chromatic_aberration / 1000.0;
	float r = texture(SCREEN_TEXTURE, vec2(uv.x + ca, uv.y)).r;
	float g = texture(SCREEN_TEXTURE, uv).g;
	float b = texture(SCREEN_TEXTURE, vec2(uv.x - ca, uv.y)).b;
	vec3 color = vec3(r, g, b);

	// Scanlines
	float scanline = sin(uv.y * 800.0) * 0.5 + 0.5;
	color *= 1.0 - scanline_strength * scanline;

	// Vignette
	float dist = distance(uv, vec2(0.5));
	color *= 1.0 - vignette_strength * dist * dist * 4.0;

	// Flicker
	float flicker = 1.0 - flicker_strength * sin(TIME * flicker_speed * 6.283);
	color *= flicker;

	COLOR = vec4(color, 1.0);
}
