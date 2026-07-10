#!/usr/bin/env node
/**
 * Headless smoke test for mobile board picker bottom sheet.
 * Usage: node scripts/test-mobile-picker.cjs [baseUrl]
 */
const { chromium } = require("/home/snaco30/.npm/_npx/9833c18b2d85bc59/node_modules/playwright");

const BASE_URL = process.argv[2] || "http://127.0.0.1:7002";
const CHROME_PATH =
    process.env.PLAYWRIGHT_CHROME_PATH ||
    `${process.env.HOME}/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome`;

async function assert(condition, message) {
    if (!condition) throw new Error(message);
}

async function main() {
    const browser = await chromium.launch({
        executablePath: CHROME_PATH,
        headless: true,
    });

    try {
        const context = await browser.newContext({
            viewport: { width: 390, height: 844 },
            isMobile: true,
            hasTouch: true,
        });
        await context.addInitScript(() => {
            localStorage.setItem("vcall_token", "smoke-test-token");
            localStorage.setItem("vcall_username", "admin");
        });

        const page = await context.newPage();
        await page.goto(`${BASE_URL}/board`, { waitUntil: "domcontentloaded" });

        const pickerBtn = page.locator("#mobileBoardPickerBtn");
        await pickerBtn.waitFor({ state: "visible", timeout: 10000 });

        const navHeight = await page.evaluate(() => {
            const nav = document.querySelector("nav");
            const bar = document.getElementById("mobileBoardPickerBar");
            const navRect = nav?.getBoundingClientRect();
            const barRect = bar?.getBoundingClientRect();
            const cssTop = bar ? getComputedStyle(bar).top : "";
            const cssVar = getComputedStyle(document.documentElement).getPropertyValue("--board-nav-height");
            return {
                navBottom: navRect ? navRect.bottom : 0,
                barTop: barRect ? barRect.top : 0,
                cssTop,
                cssVar: cssVar.trim(),
            };
        });

        console.log("nav/layout:", navHeight);
        assert(Number.parseFloat(navHeight.cssVar) >= 52, "nav height CSS variable should be set");

        await pickerBtn.click();

        const sheetState = await page.evaluate(() => {
            const sheet = document.getElementById("boardPickerSheet");
            const panel = sheet?.querySelector(".board-picker-panel");
            return {
                classes: sheet?.className || "",
                display: sheet ? getComputedStyle(sheet).display : "missing",
                panelTransform: panel ? getComputedStyle(panel).transform : "missing",
            };
        });

        console.log("sheet:", sheetState);
        assert(sheetState.classes.includes("is-open"), "sheet should have is-open class");
        assert(sheetState.display !== "none", "sheet should be visible");
        assert(sheetState.panelTransform.includes("0"), "panel should slide up");

        await page.locator("#boardPickerCloseBtn").click();
        await page.waitForTimeout(350);

        const closed = await page.evaluate(() => {
            const sheet = document.getElementById("boardPickerSheet");
            return {
                classes: sheet?.className || "",
                display: sheet ? getComputedStyle(sheet).display : "missing",
            };
        });
        console.log("closed:", closed);
        assert(!closed.classes.includes("is-open"), "sheet should close");

        const desktopContext = await browser.newContext({
            viewport: { width: 1280, height: 800 },
        });
        await desktopContext.addInitScript(() => {
            localStorage.setItem("vcall_token", "smoke-test-token");
            localStorage.setItem("vcall_username", "admin");
        });
        const desktopPage = await desktopContext.newPage();
        await desktopPage.goto(`${BASE_URL}/board`, { waitUntil: "domcontentloaded" });
        const barVisible = await desktopPage.locator("#mobileBoardPickerBar").isVisible();
        assert(!barVisible, "mobile picker bar should be hidden on desktop");
        await desktopContext.close();

        console.log("OK: mobile picker smoke test passed");
    } finally {
        await browser.close();
    }
}

main().catch((error) => {
    console.error("FAIL:", error.message);
    process.exit(1);
});
