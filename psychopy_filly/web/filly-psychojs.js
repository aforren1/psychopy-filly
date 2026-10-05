// Run-time support for psychopy-filly components in PsychoJS: the browser counterpart of
// psychopy_filly/runtime.py. Generated experiment code calls init(), SceneStim.create(), and
// SceneModel.create().
//
// filly renders into a texture that PIXI (PsychoJS's renderer) owns, in PIXI's own WebGL2
// context, and PIXI draws it as a sprite: nothing is copied. filly.js explains how the two
// renderers share the context; this module hands the context back at PIXI's "prerender".
//
// PsychoJS updates a stimulus after the frame in which its parameters change, for every
// stimulus type, so a change shows one frame later than in PsychoPy.

import { createRenderer, FillyError, InteropError } from "./filly.js";

export { FillyError };

let psychojs = null;  // { util, visual } of the experiment's PsychoJS
const hosts = new Map();  // PsychoJS Window -> Host

/** Give this module the experiment's PsychoJS namespaces; the generated code calls it once. */
export function init({ util, visual })
{
	psychojs = { util, visual };
	SceneStim = defineSceneStim(visual, util);
}

// The SceneStim class, defined by init() because it extends the experiment's VisualStim.
export let SceneStim = null;

class Host
{
	static async create(win)
	{
		const pixi = win._renderer;
		const gl = pixi && pixi.gl;
		if (typeof WebGL2RenderingContext === "undefined" || !(gl instanceof WebGL2RenderingContext))
		{
			// PIXI uses WebGL1 on non-Apple mobile devices.
			throw new InteropError("3D stimuli need WebGL2, but PsychoJS created a WebGL1 context on this device");
		}
		const renderer = await createRenderer(gl, { onHandBack: () => pixi.reset() });
		const host = new Host(win, pixi, renderer);
		// PIXI draws the sprites only after filly has handed the context back.
		pixi.on("prerender", host.handBack);
		return host;
	}

	constructor(win, pixi, renderer)
	{
		this.win = win;
		this.pixi = pixi;
		this.renderer = renderer;
		this.stims = new Set();
		this.transparentReady = false;  // whether a transparent scene has rendered
		this.modelCache = new ModelCache(renderer);
		this.handBack = () => this.renderer.handBack();
		// PsychoJS bundles PIXI without exporting it; reach its classes through the window.
		const sprite = win._backgroundSprite;
		this.Sprite = sprite.constructor;
		this.Texture = sprite.texture.constructor;
		this.BaseTexture = sprite.texture.baseTexture.constructor;
	}

	close()
	{
		for (const stim of [...this.stims])
		{
			stim.close();
		}
		this.pixi.off("prerender", this.handBack);
		try
		{
			this.modelCache.close();
		}
		finally
		{
			this.renderer.close();
		}
	}
}

async function hostFor(win)
{
	if (!hosts.has(win))
	{
		hosts.set(win, Host.create(win));
	}
	try
	{
		return await hosts.get(win);
	}
	catch (error)
	{
		hosts.delete(win);
		throw error;
	}
}

/** The open scenes of all windows, for tests and debugging. */
export async function stimuli()
{
	const all = [];
	for (const promise of hosts.values())
	{
		all.push(...(await promise).stims);
	}
	return all;
}

/** Close all stimuli and renderers that this module created. Repeated calls are valid. */
export async function closeAll()
{
	const pending = [...hosts.values()];
	hosts.clear();
	for (const promise of pending)
	{
		try
		{
			(await promise).close();
		}
		catch (error)
		{
			// A host that failed to start has nothing to close.
		}
	}
}

// --- value conversion: the same rules as runtime.py ------------------------------------------

function blank(value)
{
	return value === undefined || value === null || (typeof value === "string" && ["", "None", "none"].includes(value.trim()));
}

function vector(value, name, size = 3)
{
	const values = (Array.isArray(value) || ArrayBuffer.isView(value) ? Array.from(value) : [value]).map(Number);
	if (values.length !== size || !values.every(Number.isFinite))
	{
		throw new RangeError(`${name} needs ${size} finite numbers, got ${JSON.stringify(value)}`);
	}
	return values;
}

function scale(value)
{
	let values = Array.isArray(value) ? value.map(Number) : [Number(value)];
	if (values.length === 1)
	{
		values = [values[0], values[0], values[0]];
	}
	if (values.length !== 3 || !values.every((v) => Number.isFinite(v) && v !== 0))
	{
		throw new RangeError(`modelScale needs 1 or 3 nonzero numbers, got ${JSON.stringify(value)}`);
	}
	return values;
}

function number(value, name, low = -Infinity, high = Infinity, lowOpen = false)
{
	const n = Number(value);
	if (!(lowOpen ? low < n : low <= n) || !(n <= high))
	{
		throw new RangeError(`${name} must be in ${lowOpen ? "(" : "["}${low}, ${high}], got ${JSON.stringify(value)}`);
	}
	return n;
}

function srgbToLinear(v)
{
	v = Math.min(Math.max(v, 0), 1);
	return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

// PsychoPy color spaces that PsychoJS supports.
const COLOR_SPACES = { rgb: "RGB", named: "RGB", hex: "RGB", rgb255: "RGB255" };

// A PsychoPy color as linear RGBA in [0, 1]: PsychoPy colors are display values, filly's inputs
// are linear, and filly encodes its output to sRGB, so an unlit surface shows the given color.
function linearColor(value, space, name)
{
	const { util } = psychojs;
	const key = COLOR_SPACES[space];
	if (!key)
	{
		throw new RangeError(`${name}: PsychoJS has no color space ${JSON.stringify(space)}; use rgb, rgb255, hex, or named`);
	}
	const color = value instanceof util.Color ? value : new util.Color(value, util.Color.COLOR_SPACE[key]);
	return [...color.rgb.map(srgbToLinear), 1];
}

// A filly lookup key: a name if it exists, else an index given as text or a number.
function key(value, names)
{
	if (typeof value === "number" && Number.isInteger(value))
	{
		return value;
	}
	const text = String(value).trim();
	return names.includes(text) || !/^\d+$/.test(text) ? text : Number(text);
}

// filly applies Euler rotations about X, then Y, then Z: R = Rz Ry Rx. Row-major 3 x 3.
function eulerMatrix([x, y, z])
{
	[x, y, z] = [x, y, z].map((d) => d * Math.PI / 180);
	const [cx, sx, cy, sy, cz, sz] = [Math.cos(x), Math.sin(x), Math.cos(y), Math.sin(y), Math.cos(z), Math.sin(z)];
	return [
		[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
		[sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
		[-sy, cy * sx, cy * cx],
	];
}

const DEFAULTS = {
	rotation: [0, 0, 0], modelPos: [0, 0, 0], modelScale: [1, 1, 1], fov: 30, lookAt: [0, 0, 0], fill: 0.9,
	lightDir: [-1, -1, -2], lightIntensity: 100000, lightColor: [1, 1, 1, 1], envIntensity: 20000,
	envRotation: 0, animTime: 0,
};

function resourceUrl(win, name)
{
	// PsychoJS downloads unknown file types as text, which garbles binary glTF, so the stimulus
	// fetches the file itself from the resource's path; the browser cache serves the second request.
	const resource = win.psychoJS?.serverManager?._resources?.get(name);
	return resource?.path ?? name;
}

// The 3D Model component's default model. The compile copies it next to this module, unless the
// experiment folder has its own file of this name, which PsychoJS then knows as a resource.
const DEFAULT_MODEL = "default.glb";

function modelUrl(win, name)
{
	if (name === DEFAULT_MODEL && !win.psychoJS?.serverManager?._resources?.has(name))
	{
		return new URL(DEFAULT_MODEL, import.meta.url).href;
	}
	return resourceUrl(win, name);
}

// Lets the page draw a frame between the steps of creating a stimulus. Hidden pages get no
// animation frames, so a timer stands in after 50 ms.
function nextFrame()
{
	return new Promise((resolve) =>
	{
		const timer = setTimeout(resolve, 50);
		requestAnimationFrame(() =>
		{
			clearTimeout(timer);
			resolve();
		});
	});
}

async function fetchBytes(url)
{
	const response = await fetch(url);
	if (!response.ok)
	{
		throw new FillyError(`Could not fetch ${url}: ${response.status} ${response.statusText}`);
	}
	return new Uint8Array(await response.arrayBuffer());
}

// Resolves when the GPU has finished the commands issued so far. It polls a fence between
// frames, so the page keeps drawing; gl.finish() would block it.
async function gpuDone(gl)
{
	const sync = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
	gl.flush();
	try
	{
		while (gl.clientWaitSync(sync, 0, 0) === gl.TIMEOUT_EXPIRED)
		{
			await nextFrame();
		}
	}
	finally
	{
		gl.deleteSync(sync);
	}
}

// The names of the materials whose base color a clip of the filly model animates. Applying or
// resetting any clip restores those base colors to their loaded values, so a base color setting
// must be written to them again afterwards.
function animatedBaseColors(model)
{
	const animated = new Set();
	for (const clip of model.animations)
	{
		for (const { material, property } of clip.materialProperties)
		{
			if (property === "baseColorFactor")
			{
				animated.add(material);
			}
		}
	}
	return animated;
}

// The framing box of a scene without models.
const EMPTY_BOX = [[-1, -1, -1], [1, 1, 1]];

function boxCorners([low, high])
{
	const corners = [];
	for (let i = 0; i < 8; i++)
	{
		corners.push([0, 1, 2].map((k) => ((i >> k) & 1 ? high : low)[k]));
	}
	return corners;
}

// A sphere [center, radius] that encloses all given spheres.
function mergeSpheres(spheres)
{
	let [center, radius] = spheres[0];
	for (const [otherCenter, otherRadius] of spheres.slice(1))
	{
		const offset = otherCenter.map((v, i) => v - center[i]);
		const distance = Math.hypot(...offset);
		if (distance + otherRadius <= radius)
		{
			continue;
		}
		if (distance + radius <= otherRadius)
		{
			[center, radius] = [otherCenter, otherRadius];
			continue;
		}
		const newRadius = (distance + radius + otherRadius) / 2;
		center = center.map((v, i) => v + offset[i] / distance * (newRadius - radius));
		radius = newRadius;
	}
	return [center, radius];
}

// State that setters change and that the next render applies, in named groups.
const settings = {
	// Stores a value; returns whether it changed.
	_set(name, value, groups, log)
	{
		if (JSON.stringify(this._state[name]) === JSON.stringify(value) && name in this._state)
		{
			return false;
		}
		this._state[name] = value;
		for (const group of groups)
		{
			this._dirty.add(group);
		}
		if (groups.length)
		{
			this._changed();
		}
		if (log && this._autoLog)
		{
			this._logger()?.exp(`Set ${this.name} ${name}=${JSON.stringify(value)}`);
		}
		return true;
	},

	_default(value, name)
	{
		return blank(value) ? DEFAULTS[name] : value;
	},
};

function defineSceneStim(visual, util)
{
	/**
	 * A filly scene rendered into a texture and drawn as a sprite. SceneModel objects add models
	 * to it. The parameters and their defaults are those of psychopy_filly.runtime.SceneStim.
	 * Create it with `await SceneStim.create({...})`.
	 */
	class SceneStim extends visual.VisualStim
	{
		static async create(options)
		{
			const host = await hostFor(options.win);
			await nextFrame();
			const stim = new SceneStim(options, host);
			try
			{
				await stim._load(options);
			}
			catch (error)
			{
				stim.close();
				throw error;
			}
			return stim;
		}

		constructor({ win, name, pos = [0, 0], size, units, ori = 0, opacity, depth = 0, autoLog = false,
			colorSpace = "rgb", resolution = null, renderScale = 1 }, host)
		{
			super({ name, win, units, ori, opacity: blank(opacity) ? 1 : opacity, depth, pos, size, autoLog });
			this._host = host;
			this.colorSpace = colorSpace || "rgb";
			this._state = {};
			this._dirty = new Set();
			this._closed = true;
			this.models = [];
			this._cameraModel = null;  // the model whose file camera the scene uses, if any
			this._frameBox = EMPTY_BOX;
			this._cameraPosition = null;  // from the framing, see _applyCamera()
			this._planes = null;  // the clipping planes that the camera has
			this._loadingModels = new Set();  // the SceneModels that load a file
			if (blank(resolution))
			{
				const pixels = util.to_px(this.size, this.units, this.win);
				const density = win._renderer.resolution || 1;
				const factor = number(blank(renderScale) ? 1 : renderScale, "renderScale", 0, 2, true);
				resolution = pixels.map((v) => Math.abs(v) * density * factor);
			}
			[this._width, this._height] = vector(resolution, "resolution", 2)
				.map((v) => Math.min(Math.max(Math.round(v), 1), 8192));
			this._aspect = this._width / this._height;
		}

		async _load(options)
		{
			const o = options;
			if (!["perspective", "orthographic", undefined, null].includes(o.projection))
			{
				throw new RangeError(`projection must be 'perspective' or 'orthographic', not ${JSON.stringify(o.projection)}`);
			}
			const environment = blank(o.environment) ? "uniform" : o.environment;
			if (!["uniform", "none", "file"].includes(environment))
			{
				throw new RangeError(`environment must be 'uniform', 'none', or 'file', not ${JSON.stringify(environment)}`);
			}
			if (environment === "file" && blank(o.envFile))
			{
				throw new RangeError("environment='file' needs envFile");
			}
			this._projection = o.projection || "perspective";
			const limit = cacheLimit(o.modelCacheMiB);
			const cache = this._host.modelCache;
			if (limit !== null)
			{
				if (cache.limit === null)
				{
					cache.limit = limit;
				}
				else if (cache.limit !== limit)
				{
					// One cache per window: the first scene that sets the limit decides.
					console.warn(`filly: modelCacheMiB=${o.modelCacheMiB} ignored: the window's model cache already has a limit of ${cache.limit / 2 ** 20} MiB`);
				}
			}

			const { renderer } = this._host;
			const scene = this._scene = renderer.createScene();
			scene.refraction = this._refraction = Boolean(o.refraction);  // before loading: glass needs it at load
			scene.toneMapping = o.toneMapping || "linear";
			scene.antialiasing = o.antialiasing || "fxaa";
			scene.msaa = Number(o.msaa || 1);
			scene.shadows = Boolean(o.shadows);
			this.camera = scene.createCamera();
			scene.camera = this.camera;
			this.light = null;
			if (o.light ?? true)
			{
				this.light = scene.addDirectionalLight({ direction: DEFAULTS.lightDir });
				this.light.castsShadows = Boolean(o.shadows);
			}
			if (environment === "uniform")
			{
				scene.setEnvironment(new Float32Array(8 * 16 * 3).fill(1), 16, 8);
			}
			else if (environment === "file")
			{
				const bytes = await fetchBytes(resourceUrl(this.win, o.envFile));
				if (String(o.envFile).toLowerCase().endsWith(".ktx"))
				{
					scene.loadEnvironmentKtx(bytes);
				}
				else
				{
					scene.loadEnvironment(bytes);
				}
			}
			this._hasEnvironment = environment !== "none";
			scene.environmentVisible = Boolean(o.envVisible);
			// The visible environment is opaque and covers the background.
			this._opaqueEnvironment = this._hasEnvironment && Boolean(o.envVisible);
			await nextFrame();

			this._host.stims.add(this);
			this._closed = false;
			this.setFov(o.fov, false);
			this.setViewHeight(o.viewHeight, false);
			this.setCamPos(o.camPos, false);
			this.setLookAt(o.lookAt, false);
			this.setNear(o.near, false);
			this.setFar(o.far, false);
			this.setFill(o.fill, false);
			this.setExposure(o.exposure, false);
			this.setLightDir(o.lightDir, false);
			this.setLightIntensity(o.lightIntensity, false);
			this.setLightColor(o.lightColor, false);
			this.setEnvIntensity(o.envIntensity, false);
			this.setEnvRotation(o.envRotation, false);
			this.setBackgroundColor(o.backgroundColor, false);
			this._createTarget();
			this._host.renderer.handBack();
		}

		get closed()
		{
			return this._closed;
		}

		_changed()
		{
			this._needUpdate = true;
		}

		_logger()
		{
			return this.psychoJS?.experimentLogger;
		}

		// --- models --------------------------------------------------------------------------

		// Fits the framing box to the models again, after a model loaded or closed.
		_modelsChanged()
		{
			const boxes = this.models.map((model) => model._frameBox);
			this._frameBox = boxes.length
				? [[0, 1, 2].map((i) => Math.min(...boxes.map((box) => box[0][i]))),
					[0, 1, 2].map((i) => Math.max(...boxes.map((box) => box[1][i])))]
				: EMPTY_BOX;
			this._dirty.add("camera");
			this._needUpdate = true;
		}

		// Renders through `camera`, a camera in `model`'s file; null: the scene's own camera.
		_useCamera(model, camera)
		{
			if (camera === null)
			{
				if (this._cameraModel === model)
				{
					this._cameraModel = null;
					this._scene.camera = this.camera;
					this._dirty.add("camera");
					this._dirty.add("exposure");
				}
				return;
			}
			if (this._cameraModel !== null && this._cameraModel !== model)
			{
				throw new RangeError(`${this.name}: ${this._cameraModel.name} already provides the scene's camera from its file; only one model can`);
			}
			this._cameraModel = model;
			this._scene.camera = camera;
			this._dirty.add("camera");
			this._dirty.add("exposure");
		}

		// --- camera, lighting, and appearance ------------------------------------------------
		// The camera's position depends on the framing; the automatic clipping planes ("clip")
		// also depend on the models' poses, which can change in every frame.

		setFov(fov, log = false)
		{
			this._set("fov", number(this._default(fov, "fov"), "fov", 0, 180, true), ["camera"], log);
		}

		setViewHeight(viewHeight, log = false)
		{
			this._set("viewHeight", blank(viewHeight) ? null : number(viewHeight, "viewHeight", 0, Infinity, true), ["camera"], log);
		}

		setCamPos(camPos, log = false)
		{
			this._set("camPos", blank(camPos) ? null : vector(camPos, "camPos"), ["camera"], log);
		}

		setLookAt(lookAt, log = false)
		{
			this._set("lookAt", vector(this._default(lookAt, "lookAt"), "lookAt"), ["camera"], log);
		}

		setNear(near, log = false)
		{
			this._set("near", blank(near) ? null : number(near, "near", 0, Infinity, true), ["clip"], log);
		}

		setFar(far, log = false)
		{
			this._set("far", blank(far) ? null : number(far, "far", 0, Infinity, true), ["clip"], log);
		}

		setFill(fill, log = false)
		{
			this._set("fill", number(this._default(fill, "fill"), "fill", 0, 1, true), ["camera"], log);
		}

		setExposure(exposure, log = false)
		{
			this._set("exposure", blank(exposure) ? null : number(exposure, "exposure", -10, 24), ["exposure"], log);
		}

		setLightDir(lightDir, log = false)
		{
			const value = vector(this._default(lightDir, "lightDir"), "lightDir");
			if (value.every((v) => v === 0))
			{
				throw new RangeError("lightDir must not be zero");
			}
			this._set("lightDir", value, ["light"], log);
		}

		setLightIntensity(lightIntensity, log = false)
		{
			this._set("lightIntensity", number(this._default(lightIntensity, "lightIntensity"), "lightIntensity", 0), ["light"], log);
		}

		setLightColor(lightColor, log = false)
		{
			const value = blank(lightColor) ? DEFAULTS.lightColor : linearColor(lightColor, this.colorSpace, "lightColor");
			this._set("lightColor", value, ["light"], log);
		}

		setEnvIntensity(envIntensity, log = false)
		{
			this._set("envIntensity", number(this._default(envIntensity, "envIntensity"), "envIntensity", 0), ["environment"], log);
		}

		setEnvRotation(envRotation, log = false)
		{
			this._set("envRotation", number(this._default(envRotation, "envRotation"), "envRotation"), ["environment"], log);
		}

		setBackgroundColor(backgroundColor, log = false)
		{
			const value = blank(backgroundColor) ? null : linearColor(backgroundColor, this.colorSpace, "backgroundColor");
			this._set("backgroundColor", value, ["background"], log);
		}

		/** Render again at the next update, after direct changes to filly objects. */
		invalidate()
		{
			this._dirty.add("render");
			this._needUpdate = true;
		}

		// --- applying state ------------------------------------------------------------------

		// Places the scene's camera and sets its planes. Without camPos, the position depends on
		// the framing box, fill, fov, and aspect only, so pose changes need only _applyClip().
		_applyCamera()
		{
			const state = this._state;
			if (this._cameraModel !== null)
			{
				return;
			}
			const camera = this.camera;
			const orthographic = this._projection === "orthographic";
			// frame() places the camera for the default position; the planes are placeholders.
			if (orthographic)
			{
				camera.setOrthographic({ height: 1, near: 0.1, far: 1 });
			}
			else
			{
				camera.setPerspective({ fovY: state.fov, near: 0.1, far: 1 });
			}
			camera.frame(this._frameBox, { fill: state.fill, direction: [0, 0, -1], aspect: this._aspect });
			let position = camera.position;
			if (state.camPos !== null)
			{
				position = state.camPos;
				const target = state.lookAt;
				const d = target.map((v, i) => v - position[i]);
				const length = Math.hypot(...d);
				if (length < 1e-9)
				{
					throw new RangeError(`${this.name}: camPos and lookAt are the same point`);
				}
				camera.position = position;
				// lookAt needs an up vector that is not parallel to the view direction.
				camera.lookAt(target, Math.abs(d[1] / length) > 0.999 ? [0, 0, -1] : [0, 1, 0]);
			}
			this._cameraPosition = position;
			if (orthographic)
			{
				// The framing height: the framing box's bounding sphere spans `fill` of the
				// narrower axis.
				const [low, high] = this._frameBox;
				const diagonal = Math.hypot(...high.map((v, i) => v - low[i]));
				this._viewHeight = state.viewHeight ?? diagonal / state.fill / Math.min(1, this._aspect);
			}
			this._planes = null;  // frame() replaced them
			this._applyClip();
		}

		// Sets the clipping planes. The default planes enclose the models' bounding spheres at
		// their current poses.
		_applyClip()
		{
			const state = this._state;
			if (this._cameraModel !== null)
			{
				return;
			}
			const [low, high] = this._frameBox;
			const [center, radius] = this.models.length
				? mergeSpheres(this.models.map((model) => model._sphere()))
				: [low.map((v, i) => (v + high[i]) / 2), 1];
			const position = this._cameraPosition;
			const distance = Math.hypot(center[0] - position[0], center[1] - position[1], center[2] - position[2]);
			const near = state.near ?? Math.max(distance - 1.05 * radius, 0.01 * radius);
			const far = state.far ?? distance + 1.05 * radius;
			if (far <= near)
			{
				throw new RangeError(`${this.name}: far (${far}) must be greater than near (${near})`);
			}
			// A model that turns about its center keeps its sphere, and the planes stay.
			if (this._planes !== null && this._planes[0] === near && this._planes[1] === far)
			{
				return;
			}
			this._planes = [near, far];
			if (this._projection === "orthographic")
			{
				this.camera.setOrthographic({ height: this._viewHeight, near, far });
			}
			else
			{
				this.camera.setPerspective({ fovY: state.fov, near, far });
			}
		}

		_apply()
		{
			const dirty = this._dirty;
			const state = this._state;
			if (dirty.has("camera"))
			{
				this._applyCamera();
			}
			else if (dirty.has("clip"))
			{
				this._applyClip();
			}
			if (dirty.has("exposure") && state.exposure !== null)
			{
				this._scene.camera.exposure = state.exposure;
			}
			if (dirty.has("light") && this.light)
			{
				this.light.direction = state.lightDir;
				this.light.intensity = state.lightIntensity;
				this.light.color = state.lightColor.slice(0, 3);
			}
			if (dirty.has("environment") && this._hasEnvironment)
			{
				this._scene.environmentIntensity = state.envIntensity;
				this._scene.environmentRotation = state.envRotation;
			}
			if (dirty.has("background"))
			{
				const background = state.backgroundColor;
				// Transparent output composites the models over the window and earlier stimuli.
				// It costs Filament an extra pass, so it is on only where the image can have alpha
				// below one.
				this._scene.transparent = !this._opaqueEnvironment && (background === null || background[3] < 1);
				this._scene.background = background ?? [0, 0, 0, 0];
			}
			dirty.clear();
		}

		// --- drawing -------------------------------------------------------------------------

		// A PIXI texture without a resource: PIXI allocates RGBA8 storage at its first bind.
		// Premultiplied alpha mode, because filly writes premultiplied color.
		_createTarget()
		{
			const host = this._host;
			host.renderer.handBack();
			if (this._target)
			{
				this._target.close();
				this._target.dispose();
			}
			this._baseTexture ??= new host.BaseTexture(null,
				{ width: this._width, height: this._height, alphaMode: 2, mipmap: 0, scaleMode: 1 });
			const textures = host.pixi.texture;
			textures.bind(this._baseTexture);
			// PIXI's texture garbage collection deletes the GL texture of a managed texture that it
			// has not drawn for a while (GC_MAX_IDLE: 3600 frames), and the next bind creates an
			// empty one. A scene hidden for a minute and shown again without a change would then
			// show nothing. The base texture's destroy() still deletes the GL texture.
			const managed = textures.managedTextures.indexOf(this._baseTexture);
			if (managed >= 0)
			{
				textures.managedTextures.splice(managed, 1);
			}
			this._glTexture = this._baseTexture._glTextures[host.pixi.CONTEXT_UID].texture;
			this._target = host.renderer.importTexture(this._glTexture, this._width, this._height);
			this._dirty.add("render");
		}

		_needsRender()
		{
			return this._dirty.size > 0 || this.models.some((model) => model._dirty.size > 0);
		}

		// Renders the scene. With apply false, the pending settings stay pending.
		_render(apply = true)
		{
			if (apply)
			{
				for (const model of this.models)
				{
					if (model._dirty.size)
					{
						model._apply();
					}
				}
				if (this._dirty.size)
				{
					this._apply();
				}
			}
			this._host.renderer.render(this._scene, this._target);
			if (apply)
			{
				this._dirty.clear();
			}
		}

		_updateIfNeeded()
		{
			if (this._closed)
			{
				return;
			}
			const host = this._host;
			// Another GL texture after a context loss: render into the new one.
			const current = this._baseTexture._glTextures[host.pixi.CONTEXT_UID];
			if (!current || current.texture !== this._glTexture)
			{
				this._createTarget();
				this._needUpdate = true;
			}
			if (!this._needUpdate)
			{
				return;
			}
			if (this._loadingModels.size)
			{
				// Not drawn while a model loads, so that no frame shows the old model with the new
				// trial's settings. _needUpdate stays, so that the window asks again next frame.
				if (this._pixi)
				{
					this._pixi.visible = false;
				}
				return;
			}
			this._needUpdate = false;
			if (this._needsRender())
			{
				this._render();
			}
			// One sprite for the stimulus's life: a new Texture of the base texture would add a
			// listener to it that Sprite.destroy() does not remove (PIXI 6), at every opacity
			// change.
			this._needPixiUpdate = false;
			if (typeof this._pixi === "undefined")
			{
				this._pixi = new host.Sprite(new host.Texture(this._baseTexture));
				this._pixi.anchor.set(0.5, 0.5);
			}
			const size = util.to_px(this.size, this.units, this.win);
			// filly's rows start at the bottom; PsychoJS flips y for images, whose rows start at
			// the top, so the sprite keeps a positive y scale.
			this._pixi.scale.x = size[0] / this._width;
			this._pixi.scale.y = size[1] / this._height;
			this._pixi.position = util.to_pixiPoint(this.pos, this.units, this.win);
			this._pixi.rotation = -this.ori * Math.PI / 180;
			this._pixi.alpha = this.opacity;
			this._pixi.zIndex = -this._depth;
			this._pixi.visible = true;
		}

		close()
		{
			if (this._closed)
			{
				return;
			}
			this._closed = true;
			if (this.autoDraw)
			{
				this.setAutoDraw(false);
			}
			try
			{
				for (const model of [...this.models])
				{
					model.close();
				}
				this._target?.close();
				this._scene?.close();
			}
			finally
			{
				for (const handle of [this._target, this._scene, this.camera, this.light])
				{
					handle?.dispose();
				}
				// With the sprite's own texture, which releases its listener on the base texture.
				this._pixi?.destroy({ texture: true });
				this._baseTexture?.destroy();
				this._pixi = undefined;
				this._host.stims.delete(this);
			}
		}
	}
	Object.assign(SceneStim.prototype, settings);
	return SceneStim;
}

/**
 * The model cache's memory limit, as MODEL_CACHE_MAX_BYTES in psychopy_filly/runtime.py, in
 * bytes of filly's estimate (Model.memory: cpuBytes + gpuBytes). 0 turns the cache off;
 * Infinity or null removes the limit. A 3D Scene's "Model cache (MiB)" parameter overrides it for
 * its window. Change it before the experiment calls setModel().
 *
 * The CPU part lives in the WebAssembly heap, which never shrinks: an eviction lets filly reuse
 * the memory, but does not return it to the operating system. The limit thus bounds the
 * high-water mark of the cache, not its current use.
 */
export const modelCache = {
	maxBytes: 256 * 2 ** 20,
};

// A "Model cache (MiB)" value in bytes: null for blank (modelCache.maxBytes), Infinity for
// "unlimited".
function cacheLimit(value)
{
	if (blank(value))
	{
		return null;
	}
	if (typeof value === "string" && value.trim().toLowerCase() === "unlimited")
	{
		return Infinity;
	}
	return Math.round(number(value, "modelCacheMiB", 0) * 2 ** 20);
}

// Hidden prototypes of the model files that setModel() loaded in one window, as runtime.py's
// _ModelCache. A file shown again, as in conditions that alternate models, is then a clone of
// its prototype: nothing is fetched, loaded, or uploaded again. Clones share the prototype's
// geometry, textures, and compiled materials, and have their own material instances, so a base
// color or variant stays with its model. The prototypes live in a hidden scene of the cache, so
// that a scene can close while other scenes of the window still clone them.
class ModelCache
{
	constructor(renderer)
	{
		this.renderer = renderer;
		this.scene = null;  // the hidden scene, made at the first prototype
		this.entries = new Map();  // key -> prototype, least recently used first
		this.tooLarge = new Set();  // keys of files above the limit, loaded without source data
		this.limit = null;  // bytes from a scene's parameter; null: modelCache.maxBytes
		this.loads = 0;  // files fetched and loaded, for tests
	}

	effectiveLimit()
	{
		const limit = this.limit ?? modelCache.maxBytes;
		return limit === null ? Infinity : limit;
	}

	static bytes(model)
	{
		const { cpuBytes, gpuBytes } = model.memory;
		return cpuBytes + gpuBytes;
	}

	/** The estimated bytes that the prototypes hold. */
	size()
	{
		let total = 0;
		for (const prototype of this.entries.values())
		{
			total += ModelCache.bytes(prototype);
		}
		return total;
	}

	// Returns a new model of the file at `url` in the filly Scene `scene`: a clone, or a load. A
	// clone keeps the material setup of its asset's load, which depends on the refraction
	// setting of the loading scene, so that setting is part of the key.
	async instance(url, scene, refraction)
	{
		url = new URL(url, document.baseURI).href;
		const key = `${refraction ? "refraction" : "plain"} ${url}`;
		const limit = this.effectiveLimit();
		if (limit === 0 || this.tooLarge.has(key))
		{
			this.loads++;
			return scene.loadUrl(url);
		}
		if (!this.entries.has(key))
		{
			this.loads++;
			// The source data alone is about the file size, so a larger file cannot fit.
			const fits = (bytes) => bytes <= limit;
			const loaded = await scene.loadUrl(url, { clonable: fits });
			if (!fits(loaded.fetchedBytes))
			{
				this.tooLarge.add(key);
				return loaded;
			}
			if (ModelCache.bytes(loaded) > limit)
			{
				// Loaded again without the source data, which the model would otherwise keep
				// while it shows. Once per file: the key remembers it.
				loaded.close();
				loaded.dispose();
				this.tooLarge.add(key);
				this.loads++;
				return scene.loadUrl(url);
			}
			// Another setModel() can have cached the file during the fetch.
			if (!this.entries.has(key))
			{
				this.scene ??= this.renderer.createScene();
				this.entries.set(key, loaded.clone({ scene: this.scene }));
				this.evict(key);
			}
			return loaded;
		}
		const prototype = this.entries.get(key);
		this.entries.delete(key);
		this.entries.set(key, prototype);
		const model = prototype.clone({ scene });
		// A clone leaves bone and animation data with the asset, so the entry can grow past the
		// limit.
		this.evict(key);
		return model;
	}

	evict(keep)
	{
		let total = this.size();
		const limit = this.effectiveLimit();
		// A prototype can close while clones of it show: they keep the shared asset.
		for (const [key, prototype] of [...this.entries])
		{
			if (total <= limit)
			{
				break;
			}
			if (key === keep)
			{
				continue;
			}
			this.entries.delete(key);
			total -= ModelCache.bytes(prototype);
			prototype.close();
			prototype.dispose();
		}
	}

	close()
	{
		for (const prototype of this.entries.values())
		{
			prototype.close();
			prototype.dispose();
		}
		this.entries.clear();
		if (this.scene)
		{
			this.scene.close();
			this.scene.dispose();
			this.scene = null;
		}
	}
}

/**
 * A glTF model in a SceneStim. Hidden until setAutoDraw(true); Builder calls it when the
 * component starts, and setAutoDraw(false) when it stops. The parameters and their defaults are
 * those of psychopy_filly.runtime.SceneModel. Create it with `await SceneModel.create({...})`.
 * Without a model file, the model is not part of the scene until setModel().
 */
export class SceneModel
{
	static async create(options)
	{
		const model = new SceneModel(options);
		await model._load(options);
		return model;
	}

	constructor({ scene, name, colorSpace = "rgb", center = true, fileCamera = null, fileLights = true,
		animLoop = true, autoLog = false, rotation, modelPos, modelScale })
	{
		if (!scene || scene.closed)
		{
			throw new FillyError(`${name ?? "model"}: needs an open SceneStim`);
		}
		this.scene = scene;
		this.name = name ?? "model";
		// Builder's routine code resets the status of components that have one.
		this.status = undefined;
		this.colorSpace = colorSpace || "rgb";
		this._autoLog = autoLog;
		this._closed = true;
		this._centerModel = center ?? true;
		this._fileCamera = blank(fileCamera) ? null : fileCamera;
		this._fileLights = fileLights !== false;
		this._animLoop = animLoop ?? true;
		this._state = { autoDraw: false };
		this._dirty = new Set();
		this._loading = null;
		this.model = null;
		this._activeCamera = null;
		// What a loaded file provides.
		this._materials = {};
		this._clips = [];
		this._variants = [];
		this._animatedColors = new Set();
		this._handles = new Map();  // material name -> filly Material, made at first use
		this._colored = new Set();  // the materials that have the base color setting
		this._matrix = null;  // for the current pose, see _modelMatrix()
		this._sphereCache = null;
		// The pose comes first: the framing box uses the pose at load time.
		this.setRotation(rotation, false);
		this.setModelPos(modelPos, false);
		this.setModelScale(modelScale, false);
	}

	async _load(o)
	{
		const scene = this.scene;
		if (!blank(o.model))
		{
			this._attach(await scene._scene.loadUrl(modelUrl(scene.win, o.model)), o.model);
			this._state.model = String(o.model);
			scene.models.push(this);
			scene._modelsChanged();
		}
		this._closed = false;
		this.setVariant(o.variant, false);
		this.setMaterial(o.material, false);
		this.setBaseColor(o.baseColor, false);
		this.setAnimation(o.animation, false);
		this.setAnimTime(o.animTime, false);
		for (const group of ["model", "visible"])
		{
			this._dirty.add(group);
		}
		if (this.model)
		{
			await nextFrame();
			await this._warmUp(true);
		}
	}

	// Compiles the GPU programs without blocking the page, where the browser supports it
	// (KHR_parallel_shader_compile; not Firefox), renders once with the model shown, and waits
	// until the GPU has finished, without blocking the page. Compilation and texture uploads then
	// fall on no trial frame. The next update renders with the real visibility. With `apply`
	// false, the model's pending settings do not apply (see setModel()).
	async _warmUp(apply)
	{
		const scene = this.scene;
		const host = scene._host;
		if (apply)
		{
			this._apply();
		}
		else
		{
			// Only the pose and the framing, which cannot fail: Filament culls a model that the
			// stale camera does not see, and would then compile nothing for it.
			this.model.transform = this._transform();
			scene._applyCamera();
		}
		await host.renderer.prepare(scene._scene);
		if (this._closed || scene.closed)
		{
			return;
		}
		this.model.visible = true;
		try
		{
			scene._render(apply);
			if (!scene._scene.transparent && !host.transparentReady)
			{
				// A blank background later switches to transparent output, whose first render
				// compiles Filament's pass for it, once per renderer.
				scene._scene.transparent = true;
				try
				{
					host.renderer.render(scene._scene, scene._target);
				}
				finally
				{
					scene._scene.transparent = false;
				}
			}
			host.transparentReady = true;
		}
		finally
		{
			this.model.visible = this._state.autoDraw;
			// The target now shows the model; the scene's next update must render the real image.
			scene._dirty.add("render");
			scene._needUpdate = true;
			host.renderer.handBack();
		}
		await gpuDone(host.pixi.gl);
	}

	// Puts a loaded model in place of the current one, if any, and derives everything that
	// depends on the file: the framing box, the materials and their loaded base colors, the clip
	// and variant names, and the file camera. A model that fails these steps is closed, and the
	// current one stays.
	_attach(loaded, name)
	{
		const materials = {};
		let camera = null;
		let low;
		let high;
		try
		{
			[low, high] = loaded.bounds;
			if (![...low, ...high].every(Number.isFinite) || low.some((v, i) => v >= high[i]))
			{
				throw new FillyError(`${name} has no geometry with finite, nonzero bounds`);
			}
			if (this._fileCamera !== null)
			{
				camera = loaded.camera(key(this._fileCamera, loaded.nodeNames));
			}
			this.scene._useCamera(this, camera);
			for (const materialName of loaded.materialNames)
			{
				const material = loaded.material(materialName);
				materials[materialName] = material.baseColor;
				material.dispose();
			}
		}
		catch (error)
		{
			camera?.dispose();
			loaded.close();
			loaded.dispose();
			throw error;
		}
		if (!this._fileLights)
		{
			for (const light of loaded.lights)
			{
				light.close();
				light.dispose();
			}
		}
		const old = this.model;
		this._activeCamera?.dispose();
		this._activeCamera = camera;
		for (const handle of this._handles.values())
		{
			handle.dispose();
		}
		this._handles = new Map();
		this._colored = new Set();
		this.model = loaded;
		if (old)
		{
			old.close();
			old.dispose();
		}
		this._boundsCenter = low.map((v, i) => (v + high[i]) / 2);
		this._radius = Math.hypot(...high.map((v, i) => v - low[i])) / 2;
		this._poseChanged();  // the center moved
		this._materials = materials;
		this._clips = loaded.animations.map((clip) => clip.name);
		this._animatedColors = animatedBaseColors(loaded);
		this._variants = loaded.variants;
		// Framing box: the rest-pose bounds, placed by the model's transform at load time.
		const { m, t } = this._modelMatrix();
		const corners = boxCorners([low, high]).map((c) => [0, 1, 2].map((i) => m[i][0] * c[0] + m[i][1] * c[1] + m[i][2] * c[2] + t[i]));
		this._frameBox = [[0, 1, 2].map((i) => Math.min(...corners.map((c) => c[i]))),
			[0, 1, 2].map((i) => Math.max(...corners.map((c) => c[i])))];
		loaded.visible = this._state.autoDraw;
	}

	get closed()
	{
		return this._closed;
	}

	get autoDraw()
	{
		return this._state.autoDraw;
	}

	_changed()
	{
		this.scene._needUpdate = true;
	}

	_logger()
	{
		return this.scene.psychoJS?.experimentLogger;
	}

	_poseChanged()
	{
		this._matrix = null;
		this._sphereCache = null;
		// The automatic clipping planes depend on every model's pose.
		this.scene._dirty.add("clip");
	}

	/**
	 * Shows another model file. Returns a promise that resolves when the model has loaded, its
	 * shaders are compiled, and its textures are on the GPU. The other settings stay and apply to
	 * the new model. Until the promise resolves, the scene is not drawn, so a frame never shows
	 * the old model with the new trial's settings. A file that a scene of the window showed before
	 * is a clone of its first load (see modelCache).
	 */
	setModel(model, log = false)
	{
		const name = String(model);
		if (this._state.model === name)
		{
			return this._loading ?? Promise.resolve();
		}
		this._set("model", name, [], log);
		const scene = this.scene;
		scene._needUpdate = true;
		const loading = (async () =>
		{
			const loaded = await scene._host.modelCache.instance(modelUrl(scene.win, name), scene._scene, scene._refraction);
			// A later setModel() or close() makes this load obsolete.
			if (this._closed || this._loading !== loading)
			{
				loaded.close();
				loaded.dispose();
				return;
			}
			this._attach(loaded, name);
			for (const group of ["model", "variant", "animation", "material", "visible"])
			{
				this._dirty.add(group);
			}
			if (!scene.models.includes(this))
			{
				scene.models.push(this);
			}
			scene._modelsChanged();
			// Builder sets the trial's other parameters after this one, so the warm-up must not
			// apply the previous trial's clip or variant: the new model may not have them.
			await this._warmUp(false);
		})();
		this._loading = loading;
		scene._loadingModels.add(this);
		const done = () =>
		{
			if (this._loading === loading)
			{
				this._loading = null;
				scene._loadingModels.delete(this);
				scene._needUpdate = true;
			}
		};
		loading.then(done, done);
		return loading;
	}

	/** Show (true) or hide (false) the model in its scene. */
	setAutoDraw(value, log = false)
	{
		this._set("autoDraw", Boolean(value), ["visible"], log);
	}

	setRotation(rotation, log = false)
	{
		if (this._set("rotation", vector(this._default(rotation, "rotation"), "rotation"), ["model"], log))
		{
			this._poseChanged();
		}
	}

	setModelPos(modelPos, log = false)
	{
		if (this._set("modelPos", vector(this._default(modelPos, "modelPos"), "modelPos"), ["model"], log))
		{
			this._poseChanged();
		}
	}

	setModelScale(modelScale, log = false)
	{
		if (this._set("modelScale", scale(this._default(modelScale, "modelScale")), ["model"], log))
		{
			this._poseChanged();
		}
	}

	setVariant(variant, log = false)
	{
		const value = blank(variant) ? null : key(variant, this._variants);
		// A variant replaces material instances, so a base color must be written again.
		this._set("variant", value, ["variant", "material"], log);
	}

	setMaterial(material, log = false)
	{
		const value = blank(material) ? null : String(material);
		// Without a model, or while a new one loads, the material names are not known; filly
		// checks the name when it applies the base color.
		if (value !== null && this.model !== null && !this._loading && !(value in this._materials))
		{
			throw new RangeError(`${this.name}: no material named ${JSON.stringify(value)}; the model has ${JSON.stringify(Object.keys(this._materials))}`);
		}
		this._set("material", value, ["material"], log);
	}

	setBaseColor(baseColor, log = false)
	{
		const value = blank(baseColor) ? null : linearColor(baseColor, this.colorSpace, "baseColor").slice(0, 3);
		this._set("baseColor", value, ["material"], log);
	}

	// Applying a clip restores the base colors that clips animate, so the base color setting is
	// written again after it, for those materials only.
	_animationGroups()
	{
		return this._animatedColors.size ? ["animation", "material"] : ["animation"];
	}

	setAnimation(animation, log = false)
	{
		const value = blank(animation) ? null : key(animation, this._clips);
		this._set("animation", value, this._animationGroups(), log);
	}

	setAnimTime(animTime, log = false)
	{
		const value = number(this._default(animTime, "animTime"), "animTime", 0);
		// Without a clip, the time changes nothing; do not render again for it.
		const groups = this._state.animation !== null && this._state.animation !== undefined ? this._animationGroups() : [];
		this._set("animTime", value, groups, log);
	}

	get rotation()
	{
		return this._state.rotation;
	}

	// Row-major 3 x 3 m and translation t: T(modelPos) R S, with the bounding-box center moved
	// to modelPos. Cached until the pose changes: a pose set in every frame needs it twice per
	// frame, for the transform and for the clipping planes.
	_modelMatrix()
	{
		if (this._matrix === null)
		{
			const r = eulerMatrix(this._state.rotation);
			const s = this._state.modelScale;
			const m = r.map((row) => row.map((v, j) => v * s[j]));
			const t = [...this._state.modelPos];
			if (this._centerModel && this._boundsCenter)
			{
				for (let i = 0; i < 3; i++)
				{
					t[i] -= m[i][0] * this._boundsCenter[0] + m[i][1] * this._boundsCenter[1] + m[i][2] * this._boundsCenter[2];
				}
			}
			this._matrix = { m, t };
		}
		return this._matrix;
	}

	// filly's transforms are row-major 4 x 4 arrays for column vectors.
	_transform()
	{
		const { m, t } = this._modelMatrix();
		return [...m[0], t[0], ...m[1], t[1], ...m[2], t[2], 0, 0, 0, 1];
	}

	// The bounding sphere at the current pose, for the scene's clipping planes.
	_sphere()
	{
		if (this._sphereCache === null)
		{
			const { m, t } = this._modelMatrix();
			const c = this._boundsCenter;
			const center = [0, 1, 2].map((i) => m[i][0] * c[0] + m[i][1] * c[1] + m[i][2] * c[2] + t[i]);
			this._sphereCache = [center, this._radius * Math.max(...this._state.modelScale.map(Math.abs))];
		}
		return this._sphereCache;
	}

	_material(name)
	{
		let handle = this._handles.get(name);
		if (!handle)
		{
			handle = this.model.material(name);
			this._handles.set(name, handle);
		}
		return handle;
	}

	// The materials that the base color setting applies to.
	_colorTargets()
	{
		const state = this._state;
		if (state.baseColor === null)
		{
			return new Set();
		}
		return new Set(state.material !== null ? [state.material] : Object.keys(this._materials));
	}

	// Writes the base color setting to `targets`, and restores the materials that it left.
	_applyColors(targets)
	{
		for (const name of this._colored)
		{
			// Animation has already restored the animated ones (see _apply()).
			if (!targets.has(name) && !this._animatedColors.has(name))
			{
				this._material(name).baseColor = this._materials[name];
			}
		}
		for (const name of targets)
		{
			const material = this._material(name);
			// An animated alpha is the clip's; any other is the loaded one.
			const alpha = this._animatedColors.has(name) ? material.baseColor[3] : this._materials[name][3];
			material.baseColor = [...this._state.baseColor, alpha];
		}
		this._colored = targets;
	}

	_apply()
	{
		const dirty = this._dirty;
		const state = this._state;
		const model = this.model;
		if (dirty.has("variant") && state.variant !== null)
		{
			model.applyVariant(state.variant);
		}
		const targets = dirty.has("material") ? this._colorTargets() : null;
		// Applying or resetting a clip also removes a base color that no longer applies from the
		// materials whose base color a clip animates.
		const restore = targets !== null && [...this._colored].some((name) => !targets.has(name) && this._animatedColors.has(name));
		if (dirty.has("animation") || restore)
		{
			if (state.animation === null)
			{
				model.resetAnimation();
			}
			else
			{
				model.applyAnimation(state.animation, state.animTime, { loop: this._animLoop });
			}
		}
		if (targets !== null)
		{
			this._applyColors(targets);
		}
		if (dirty.has("model"))
		{
			model.transform = this._transform();
		}
		if (dirty.has("visible"))
		{
			model.visible = state.autoDraw;
		}
		dirty.clear();
	}

	/** Remove the model from its scene. Repeated calls are valid. */
	close()
	{
		if (this._closed)
		{
			return;
		}
		this._closed = true;
		this._loading = null;
		const scene = this.scene;
		scene._loadingModels.delete(this);
		try
		{
			scene._useCamera(this, null);
			if (!scene.closed)
			{
				this.model?.close();
			}
		}
		finally
		{
			for (const handle of this._handles.values())
			{
				handle.dispose();
			}
			this._handles.clear();
			this._activeCamera?.dispose();
			this.model?.dispose();
			const index = scene.models.indexOf(this);
			if (index >= 0)
			{
				scene.models.splice(index, 1);
			}
			if (!scene.closed)
			{
				scene._modelsChanged();
			}
		}
	}
}
Object.assign(SceneModel.prototype, settings);
