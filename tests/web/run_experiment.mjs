// Run a compiled PsychoJS experiment in a browser and report what happened, as JSON on stdout.
//
// Usage: node run_experiment.mjs CONFIG_JSON
//
// CONFIG_JSON is a file with:
//   folder      experiment folder (index.html, the script, lib/, filly/, resources)
//   browser     "chrome", "edge", or "firefox"; executable: the browser's executable
//   screenshots [seconds after the 3D stimuli are ready, ...]; each is saved as <out>_<i>.png
//   out         path prefix for screenshots
//   read        read the first 3D scene's render target after the last screenshot
//   isolate     serve with COOP and COEP headers, which make the page cross-origin isolated
//   escape      press Escape after the last screenshot
//   url         the experiment's URL on a server that the caller runs; folder is then not served
//   setModel    a model file: when the 3D scenes are ready, call setModel() on the first model of
//               the first scene and report its material names (result.setModel)
//   evaluate    the body of an async function of (runtime, scene, model): the runtime module, and
//               the first scene and its first model. It runs when the 3D scenes are ready, before
//               the screenshots; its JSON result is result.evaluate.
// The server sends no other headers, as a plain static host.
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import puppeteer from "puppeteer-core";

const config = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const types = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
	".wasm": "application/wasm", ".css": "text/css", ".json": "application/json" };
const isolation = config.isolate ? { "Cross-Origin-Opener-Policy": "same-origin",
	"Cross-Origin-Embedder-Policy": "require-corp" } : {};
const server = config.url ? null : http.createServer((request, response) =>
{
	const file = path.join(config.folder, decodeURIComponent(new URL(request.url, "http://host").pathname));
	fs.readFile(file, (error, data) =>
	{
		if (error)
		{
			response.writeHead(404, isolation);
			response.end();
			return;
		}
		response.writeHead(200, { "Content-Type": types[path.extname(file)] ?? "application/octet-stream", ...isolation });
		response.end(data);
	});
}).listen(0);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const result = { pageErrors: [], consoleErrors: [], screenshots: [] };
const browser = await puppeteer.launch({
	executablePath: config.executable,
	browser: config.browser === "firefox" ? "firefox" : "chrome",
	headless: true,
	args: config.browser === "firefox" ? [] : ["--ignore-gpu-blocklist", "--enable-gpu"],
	defaultViewport: { width: 1000, height: 700 },
});
try
{
	const page = await browser.newPage();
	page.on("pageerror", (error) => result.pageErrors.push(error.message));
	page.on("console", (message) =>
	{
		// The favicon request is the only expected 404.
		if (message.type() === "error" && !message.text().includes("404"))
		{
			result.consoleErrors.push(message.text());
		}
	});
	if (config.page)
	{
		// A test page without PsychoJS: it stores its result in window.testResult.
		await page.goto(`http://localhost:${server.address().port}/${config.page}`);
		await page.waitForFunction(() => window.testResult !== undefined, { timeout: 60000 });
		result.page = await page.evaluate(() => window.testResult);
	}
	else
	{
		await page.goto(config.url ?? `http://localhost:${server.address().port}/index.html`);
		const ok = await page.waitForSelector("#dialogOK:not(.disabled)", { timeout: 60000 });
		await ok.click();
		// Creation time varies with machine load, so screenshot times count from the moment that
		// every 3D scene and model has started: the routine has begun, after experimentInit()
		// created them all.
		await page.waitForFunction(async () =>
		{
			const runtime = await import(new URL("filly/filly-psychojs.js", location.href).href);
			const scenes = await runtime.stimuli();
			return scenes.length > 0 && scenes.every((scene) => scene.autoDraw && scene.models.length > 0
				&& scene.models.every((model) => model.autoDraw && !model._loading));
		}, { timeout: 60000, polling: 100 });
		if (config.setModel)
		{
			result.setModel = await page.evaluate(async (name) =>
			{
				const runtime = await import(new URL("filly/filly-psychojs.js", location.href).href);
				const [scene] = await runtime.stimuli();
				const [model] = scene.models;
				const before = Object.keys(model._materials);
				const loading = model.setModel(name);
				const hiddenWhileLoading = model._loading !== null;
				await loading;
				return { before, after: Object.keys(model._materials), hiddenWhileLoading };
			}, config.setModel);
		}
		if (config.evaluate)
		{
			result.evaluate = await page.evaluate(async (body) =>
			{
				const runtime = await import(new URL("filly/filly-psychojs.js", location.href).href);
				const [scene] = await runtime.stimuli();
				const run = new Function("runtime", "scene", "model", `return (async () => { ${body} })();`);
				return await run(runtime, scene, scene.models[0]);
			}, config.evaluate);
		}
		const start = Date.now();
		for (const [index, seconds] of (config.screenshots ?? []).entries())
		{
			await sleep(Math.max(0, start + seconds * 1000 - Date.now()));
			const file = `${config.out}_${index}.png`;
			await page.screenshot({ path: file });
			result.screenshots.push(file);
		}
		Object.assign(result, await page.evaluate(() =>
		{
			const gl = document.querySelector("canvas")?.getContext("webgl2");
			const info = gl?.getExtension("WEBGL_debug_renderer_info");
			return { renderer: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : null,
				crossOriginIsolated: window.crossOriginIsolated };
		}));
		if (config.read)
		{
			result.read = await page.evaluate(async () =>
			{
				const runtime = await import(new URL("filly/filly-psychojs.js", location.href).href);
				const [stim] = await runtime.stimuli();
				return { width: stim._width, height: stim._height, pixels: Array.from(stim._target.read()) };
			});
		}
		if (config.escape)
		{
			await page.keyboard.press("Escape");
			await sleep(1500);
			result.afterEscape = await page.evaluate(async () =>
			{
				const runtime = await import(new URL("filly/filly-psychojs.js", location.href).href);
				return { stimuli: (await runtime.stimuli()).length };
			});
		}
	}
}
finally
{
	await browser.close();
	server?.close();
}
console.log(JSON.stringify(result));
