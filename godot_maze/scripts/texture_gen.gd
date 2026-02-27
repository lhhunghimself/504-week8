## Procedural retro texture generator — creates low-res textures at runtime.
## Avoids the need for external image assets.
class_name TextureGen
extends RefCounted

const TEX_SIZE := 64

static func brick_wall() -> ImageTexture:
	var img := Image.create(TEX_SIZE, TEX_SIZE, false, Image.FORMAT_RGB8)
	var mortar := Color(0.08, 0.12, 0.08)
	var brick_a := Color(0.12, 0.18, 0.12)
	var brick_b := Color(0.10, 0.15, 0.10)

	img.fill(mortar)

	# Draw brick rows
	var brick_h := 8
	var brick_w := 16
	var mortar_px := 1

	for row_idx in range(TEX_SIZE / brick_h):
		var y0 := row_idx * brick_h + mortar_px
		var offset := (brick_w / 2) if (row_idx % 2 == 1) else 0
		for col_idx in range((TEX_SIZE / brick_w) + 1):
			var x0 := col_idx * brick_w + offset + mortar_px
			var color: Color = brick_a if (row_idx + col_idx) % 2 == 0 else brick_b
			for y in range(y0, mini(y0 + brick_h - mortar_px, TEX_SIZE)):
				for x in range(x0, mini(x0 + brick_w - mortar_px, TEX_SIZE)):
					# Slight noise for texture
					var noise_val := randf_range(-0.02, 0.02)
					var c := Color(
						clampf(color.r + noise_val, 0.0, 1.0),
						clampf(color.g + noise_val, 0.0, 1.0),
						clampf(color.b + noise_val, 0.0, 1.0),
					)
					img.set_pixel(x % TEX_SIZE, y % TEX_SIZE, c)

	return ImageTexture.create_from_image(img)

static func metal_floor() -> ImageTexture:
	var img := Image.create(TEX_SIZE, TEX_SIZE, false, Image.FORMAT_RGB8)
	var base := Color(0.06, 0.08, 0.12)

	for y in range(TEX_SIZE):
		for x in range(TEX_SIZE):
			var noise_val := randf_range(-0.03, 0.03)
			var grid_line := 1.0 if ((x % 16 == 0) or (y % 16 == 0)) else 0.0
			var c := Color(
				clampf(base.r + noise_val + grid_line * 0.05, 0.0, 1.0),
				clampf(base.g + noise_val + grid_line * 0.06, 0.0, 1.0),
				clampf(base.b + noise_val + grid_line * 0.04, 0.0, 1.0),
			)
			img.set_pixel(x, y, c)

	return ImageTexture.create_from_image(img)

static func ceiling_panel() -> ImageTexture:
	var img := Image.create(TEX_SIZE, TEX_SIZE, false, Image.FORMAT_RGB8)
	var base := Color(0.03, 0.04, 0.06)

	for y in range(TEX_SIZE):
		for x in range(TEX_SIZE):
			var noise_val := randf_range(-0.01, 0.01)
			var panel_edge := 1.0 if ((x % 32 == 0) or (y % 32 == 0)) else 0.0
			var c := Color(
				clampf(base.r + noise_val + panel_edge * 0.03, 0.0, 1.0),
				clampf(base.g + noise_val + panel_edge * 0.04, 0.0, 1.0),
				clampf(base.b + noise_val + panel_edge * 0.03, 0.0, 1.0),
			)
			img.set_pixel(x, y, c)

	return ImageTexture.create_from_image(img)

static func gate_texture() -> ImageTexture:
	var img := Image.create(TEX_SIZE, TEX_SIZE, false, Image.FORMAT_RGB8)
	var base := Color(0.7, 0.45, 0.1)

	for y in range(TEX_SIZE):
		for x in range(TEX_SIZE):
			# Glowing energy barrier pattern
			var dist_center := absf(float(x) - 32.0) / 32.0
			var wave := sin(float(y) * 0.3) * 0.1
			var glow := 1.0 - dist_center + wave
			var c := Color(
				clampf(base.r * glow, 0.0, 1.0),
				clampf(base.g * glow, 0.0, 1.0),
				clampf(base.b * glow * 0.5, 0.0, 1.0),
			)
			img.set_pixel(x, y, c)

	return ImageTexture.create_from_image(img)

static func exit_portal() -> ImageTexture:
	var img := Image.create(TEX_SIZE, TEX_SIZE, false, Image.FORMAT_RGB8)
	var center := Vector2(32, 32)

	for y in range(TEX_SIZE):
		for x in range(TEX_SIZE):
			var dist := Vector2(x, y).distance_to(center) / 32.0
			var ring := sin(dist * 10.0) * 0.5 + 0.5
			var c := Color(
				clampf(0.4 * ring * (1.0 - dist), 0.0, 1.0),
				clampf(0.1 * ring, 0.0, 1.0),
				clampf(0.6 * ring * (1.0 - dist * 0.5), 0.0, 1.0),
			)
			img.set_pixel(x, y, c)

	return ImageTexture.create_from_image(img)
