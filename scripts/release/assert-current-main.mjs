const token = process.env.GITHUB_TOKEN;
const releaseSha = process.env.RELEASE_SHA;
if (!token || !/^[0-9a-f]{40}$/i.test(releaseSha ?? "")) {
  console.error("release_identity_invalid");
  process.exit(2);
}

try {
  const response = await fetch(
    "https://api.github.com/repos/paulzwecker/portfolio-app/git/ref/heads/main",
    {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      signal: AbortSignal.timeout(20_000),
    },
  );
  if (!response.ok)
    throw new Error(`github_main_recheck_failed:${response.status}`);
  const payload = await response.json();
  if (payload?.object?.sha?.toLowerCase() !== releaseSha.toLowerCase()) {
    throw new Error("release_sha_no_longer_main_tip");
  }
  console.log(`The release SHA remains the main branch tip: ${releaseSha}.`);
} catch (error) {
  console.error(
    error instanceof Error
      ? error.message
      : "release_main_recheck_failed:unknown",
  );
  process.exitCode = 1;
}
