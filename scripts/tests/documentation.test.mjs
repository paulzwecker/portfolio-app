import assert from "node:assert/strict";
import { test } from "node:test";
import { localLinks } from "../documentation.mjs";

test("Markdown links retain relative files and ignore examples and remote URLs", () => {
  const markdown = [
    "[guide](../docs/model.md#inputs)",
    "[spaced](<../docs/model guide.md>)",
    "[encoded](model%20guide.md)",
    "[web](https://example.test/guide) [mail](mailto:user@example.test) [anchor](#inputs)",
    "```md\n[example](fake.md)\n```",
  ].join("\n");
  assert.deepEqual(localLinks(markdown), [
    "../docs/model.md",
    "../docs/model guide.md",
    "model guide.md",
  ]);
});
