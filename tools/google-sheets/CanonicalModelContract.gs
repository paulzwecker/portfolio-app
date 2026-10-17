/**
 * Human-reviewed Google Sheets adapter for FinancialModelContractV1 and V2.
 * This script reads/writes portable JSON locally in the active spreadsheet; it
 * never calls the portfolio API and never recalculates model outputs.
 */
const CONTRACT_SHEET = "Contract";
const SYNC_INBOX_SHEET = "Application Model Sync Inbox";
const RISK_CONTRACT_SHEET = "Risk Assessment Contract";
const RISK_SYNC_INBOX_SHEET = "Application Risk Assessment Inbox";
const RESEARCH_CONTRACT_SHEET = "Research Revision Contract";
const RESEARCH_SYNC_INBOX_SHEET = "Application Research Inbox";
const THESIS_CONTRACT_SHEET = "Investment Thesis Contract";
const THESIS_SYNC_INBOX_SHEET = "Application Thesis Inbox";
const AGENT_ACK_CONTRACT_SHEET = "Research Agent Acknowledgment Contract";
const AGENT_ACK_SYNC_INBOX_SHEET =
  "Application Agent Work Acknowledgment Inbox";
const SYNC_INBOX_HEADERS = [
  "publish_id",
  "external_revision_id",
  "chunk_index",
  "chunk_count",
  "contract_json_chunk",
];
const SYNC_CHUNK_CHARACTERS = 40000;
const SYNC_INBOX_MAX_ROWS = 5000;

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Portfolio model")
    .addItem("Load exported contract JSON", "loadContractJson")
    .addItem("Build editable input tabs", "buildInputTabs")
    .addItem("Write edits back to contract JSON", "writeEditsToContract")
    .addItem(
      "Publish candidate to application inbox",
      "publishToApplicationInbox",
    )
    .addItem(
      "Publish risk assessment to application inbox",
      "publishRiskAssessmentToApplicationInbox",
    )
    .addItem(
      "Publish research forecast to application inbox",
      "publishResearchRevisionToApplicationInbox",
    )
    .addItem(
      "Publish investment thesis to application inbox",
      "publishInvestmentThesisToApplicationInbox",
    )
    .addItem(
      "Publish agent work acknowledgment to application inbox",
      "publishAgentAcknowledgmentToApplicationInbox",
    )
    .addToUi();
}

function publishAgentAcknowledgmentToApplicationInbox() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(
    AGENT_ACK_CONTRACT_SHEET,
  );
  if (!sheet)
    throw new Error(
      `Create the ${AGENT_ACK_CONTRACT_SHEET} tab and place one complete acknowledgment JSON object in A1.`,
    );
  const raw = String(sheet.getRange("A1").getDisplayValue() || "").trim();
  if (!raw) throw new Error(`${AGENT_ACK_CONTRACT_SHEET}!A1 is empty.`);
  const contract = JSON.parse(raw);
  const required = [
    "agent_role",
    "work_type",
    "work_key",
    "work_fingerprint",
    "external_update_id",
    "agent_run_id",
    "actor_id",
    "delivery_channel",
    "status",
    "observed_at",
  ];
  const terminal = [
    "BLOCKED",
    "SOURCE_UNAVAILABLE",
    "STALE_SOURCE",
    "UNRESOLVED_REVIEW",
  ];
  const supportedRoles = [
    "DATA_UNIVERSE_STEWARD",
    "PORTFOLIO_THESIS_SENTINEL",
    "MODEL_ALLOCATION_STEWARD",
  ];
  const supportedWorkTypes = [
    "TRIGGER",
    "QUEUE_TASK",
    "DATA_DOMAIN",
    "PORTFOLIO_STATE",
  ];
  const supportedStatuses = [
    "ACKNOWLEDGED",
    "IN_PROGRESS",
    "COMPLETED",
    "BLOCKED",
    "SOURCE_UNAVAILABLE",
    "STALE_SOURCE",
    "UNRESOLVED_REVIEW",
  ];
  if (
    !contract ||
    typeof contract !== "object" ||
    contract.contract_type !== "ResearchAgentAcknowledgmentContractV1" ||
    contract.contract_version !== "1.0.0" ||
    required.some((key) => !String(contract[key] || "").trim()) ||
    !supportedRoles.includes(contract.agent_role) ||
    !supportedWorkTypes.includes(contract.work_type) ||
    !supportedStatuses.includes(contract.status) ||
    !["API", "GOOGLE_SHEETS"].includes(contract.delivery_channel) ||
    !/^[0-9a-f]{64}$/.test(String(contract.work_fingerprint || "")) ||
    (contract.proposal_domain != null &&
      !["MODEL", "RESEARCH", "THESIS", "RISK"].includes(
        contract.proposal_domain,
      )) ||
    (terminal.includes(contract.status) &&
      !String(contract.reason || "").trim()) ||
    (contract.proposal_domain == null) !==
      (contract.proposal_candidate_id == null)
  )
    throw new Error(
      "Publish a complete ResearchAgentAcknowledgmentContractV1 version 1.0.0. Include an explicit reason for blocked or unresolved states.",
    );
  publishVersionedResearchContract_(
    contract,
    AGENT_ACK_SYNC_INBOX_SHEET,
    "Agent receipt appended for application reconciliation. It records delivery/review state only and does not accept a proposal or change investment state.",
  );
}

function publishToApplicationInbox() {
  const contract = readContract_(true);
  const candidate = contract.candidate_revision;
  const revisionId = String(candidate.source_revision_id || "").trim();
  if (!revisionId)
    throw new Error("The candidate has no external revision ID.");
  const raw = JSON.stringify(contract);
  const chunks = [];
  for (let index = 0; index < raw.length; index += SYNC_CHUNK_CHARACTERS) {
    chunks.push(raw.slice(index, index + SYNC_CHUNK_CHARACTERS));
  }
  if (chunks.length > 100)
    throw new Error(
      "The contract is too large for the application sync inbox.",
    );

  const book = SpreadsheetApp.getActive();
  let inbox = book.getSheetByName(SYNC_INBOX_SHEET);
  if (!inbox) inbox = book.insertSheet(SYNC_INBOX_SHEET);
  const header = inbox
    .getRange(1, 1, 1, SYNC_INBOX_HEADERS.length)
    .getDisplayValues()[0];
  if (header.every((cell) => !String(cell).trim())) {
    inbox
      .getRange(1, 1, 1, SYNC_INBOX_HEADERS.length)
      .setValues([SYNC_INBOX_HEADERS]);
    inbox.setFrozenRows(1);
  } else if (
    SYNC_INBOX_HEADERS.some((value, index) => header[index] !== value)
  ) {
    throw new Error(
      "The application sync inbox header does not match the required contract.",
    );
  }

  const lastRow = inbox.getLastRow();
  if (lastRow > 1) {
    const existing = inbox
      .getRange(2, 1, lastRow - 1, SYNC_INBOX_HEADERS.length)
      .getDisplayValues();
    const sameRevision = existing.filter((row) => row[1] === revisionId);
    const existingChunks = sameRevision
      .slice()
      .sort((left, right) => Number(left[2]) - Number(right[2]));
    const existingRaw = existingChunks.map((row) => row[4]).join("");
    const expectedCount = existingChunks.length
      ? Number(existingChunks[0][3])
      : 0;
    if (
      expectedCount === existingChunks.length &&
      existingChunks.every((row, index) => Number(row[2]) === index + 1) &&
      existingRaw === raw
    ) {
      SpreadsheetApp.getUi().alert(
        "This exact external revision is already in the application inbox.",
      );
      return;
    }
  }

  const startRow = Math.max(2, lastRow + 1);
  const endRow = startRow + chunks.length - 1;
  if (endRow > SYNC_INBOX_MAX_ROWS + 1)
    throw new Error("The application sync inbox reached its 5,000-row limit.");
  if (endRow > inbox.getMaxRows())
    inbox.insertRowsAfter(inbox.getMaxRows(), endRow - inbox.getMaxRows());
  const publishId = Utilities.getUuid();
  const values = chunks.map((chunk, index) => [
    publishId,
    revisionId,
    String(index + 1),
    String(chunks.length),
    chunk,
  ]);
  inbox
    .getRange(startRow, 1, values.length, SYNC_INBOX_HEADERS.length)
    .setNumberFormat("@");
  inbox
    .getRange(startRow, 1, values.length, SYNC_INBOX_HEADERS.length)
    .setValues(values);
  SpreadsheetApp.getUi().alert(
    "Candidate appended to the application inbox. The app will validate and preview it; canonical model state changes only after an explicit review and acceptance.",
  );
}

function publishRiskAssessmentToApplicationInbox() {
  const book = SpreadsheetApp.getActive();
  const contractSheet = book.getSheetByName(RISK_CONTRACT_SHEET);
  if (!contractSheet)
    throw new Error(
      'Create the "Risk Assessment Contract" tab and place the complete JSON contract in A1.',
    );
  const raw = String(
    contractSheet.getRange("A1").getDisplayValue() || "",
  ).trim();
  if (!raw) throw new Error("The risk-assessment contract cell A1 is empty.");
  const contract = JSON.parse(raw);
  assertRiskAssessmentContract_(contract);

  const revisionId = String(contract.external_revision_id).trim();
  const chunks = [];
  for (let index = 0; index < raw.length; index += SYNC_CHUNK_CHARACTERS) {
    chunks.push(raw.slice(index, index + SYNC_CHUNK_CHARACTERS));
  }
  if (chunks.length > 100)
    throw new Error(
      "The risk-assessment contract is too large for the application inbox.",
    );

  let inbox = book.getSheetByName(RISK_SYNC_INBOX_SHEET);
  if (!inbox) inbox = book.insertSheet(RISK_SYNC_INBOX_SHEET);
  const header = inbox
    .getRange(1, 1, 1, SYNC_INBOX_HEADERS.length)
    .getDisplayValues()[0];
  if (header.every((cell) => !String(cell).trim())) {
    inbox
      .getRange(1, 1, 1, SYNC_INBOX_HEADERS.length)
      .setValues([SYNC_INBOX_HEADERS]);
    inbox.setFrozenRows(1);
  } else if (
    SYNC_INBOX_HEADERS.some((value, index) => header[index] !== value)
  ) {
    throw new Error(
      "The risk-assessment inbox header does not match the application's chunked contract format.",
    );
  }

  const lastRow = inbox.getLastRow();
  if (lastRow > 1) {
    const rows = inbox
      .getRange(2, 1, lastRow - 1, SYNC_INBOX_HEADERS.length)
      .getDisplayValues();
    const matching = rows.filter((row) => row[1] === revisionId);
    if (matching.length) {
      const ordered = matching
        .slice()
        .sort((left, right) => Number(left[2]) - Number(right[2]));
      const priorRaw = ordered.map((row) => row[4]).join("");
      const expectedCount = Number(ordered[0][3]);
      if (
        expectedCount === ordered.length &&
        ordered.every((row, index) => Number(row[2]) === index + 1) &&
        priorRaw === raw
      ) {
        SpreadsheetApp.getUi().alert(
          "This exact risk-assessment revision is already in the application inbox.",
        );
        return;
      }
      throw new Error(
        "This external risk revision ID already has different or incomplete inbox content. Use a new revision ID.",
      );
    }
  }

  const startRow = Math.max(2, lastRow + 1);
  const endRow = startRow + chunks.length - 1;
  if (endRow > SYNC_INBOX_MAX_ROWS + 1)
    throw new Error("The risk-assessment inbox reached its 5,000-row limit.");
  if (endRow > inbox.getMaxRows())
    inbox.insertRowsAfter(inbox.getMaxRows(), endRow - inbox.getMaxRows());
  const publishId = Utilities.getUuid();
  const values = chunks.map((chunk, index) => [
    publishId,
    revisionId,
    String(index + 1),
    String(chunks.length),
    chunk,
  ]);
  inbox
    .getRange(startRow, 1, values.length, SYNC_INBOX_HEADERS.length)
    .setNumberFormat("@");
  inbox
    .getRange(startRow, 1, values.length, SYNC_INBOX_HEADERS.length)
    .setValues(values);
  SpreadsheetApp.getUi().alert(
    "Risk assessment appended for application review. Acceptance remains explicit and does not change portfolio holdings, targets, models or canonical Risk scores.",
  );
}

function publishResearchRevisionToApplicationInbox() {
  const contract = readVersionedResearchContract_(
    RESEARCH_CONTRACT_SHEET,
    "ResearchRevisionContractV1",
  );
  const evidence = Array.isArray(contract.evidence) ? contract.evidence : [];
  if (
    !Array.isArray(contract.forecasts) &&
    !Array.isArray(contract.assessments)
  )
    throw new Error(
      "The research contract must contain forecast or assessment arrays.",
    );
  if (!evidence.length)
    throw new Error(
      "Add at least one source evidence item before publication.",
    );
  publishVersionedResearchContract_(
    contract,
    RESEARCH_SYNC_INBOX_SHEET,
    "Research proposal appended for explicit application review. It remains separate from consensus and model assumptions.",
  );
}

function publishInvestmentThesisToApplicationInbox() {
  const contract = readVersionedResearchContract_(
    THESIS_CONTRACT_SHEET,
    "InvestmentThesisContractV1",
  );
  const claims = Array.isArray(contract.claims) ? contract.claims : [];
  const hasEvidence = claims.some(
    (claim) => Array.isArray(claim.evidence) && claim.evidence.length > 0,
  );
  if (!hasEvidence)
    throw new Error("At least one thesis claim must include source evidence.");
  publishVersionedResearchContract_(
    contract,
    THESIS_SYNC_INBOX_SHEET,
    "Thesis revision appended for explicit application review. It remains an opinion with source-linked claims.",
  );
}

function readVersionedResearchContract_(sheetTitle, expectedType) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(sheetTitle);
  if (!sheet)
    throw new Error(
      `Create the ${sheetTitle} tab and place one complete contract JSON object in A1.`,
    );
  const raw = String(sheet.getRange("A1").getDisplayValue() || "").trim();
  if (!raw) throw new Error(`${sheetTitle}!A1 is empty.`);
  const contract = JSON.parse(raw);
  const required = [
    "company_id",
    "stream_key",
    "external_revision_id",
    "author_id",
    "source_id",
    "source_reference",
    "observed_at",
    "rationale",
  ];
  if (
    !contract ||
    typeof contract !== "object" ||
    contract.contract_type !== expectedType ||
    !(expectedType === "ResearchRevisionContractV1" ||
    expectedType === "InvestmentThesisContractV1"
      ? ["1.0.0", "1.1.0"].includes(contract.contract_version)
      : contract.contract_version === "1.0.0") ||
    !Object.prototype.hasOwnProperty.call(contract, "supersedes_revision_id") ||
    (contract.supersedes_revision_id !== null &&
      !String(contract.supersedes_revision_id || "").trim()) ||
    required.some((key) => !String(contract[key] || "").trim())
  )
    throw new Error(
      `The JSON must be a complete ${expectedType} version 1.0.0 contract with exact company identity, base revision, author, source and observation time.`,
    );
  return contract;
}

function publishVersionedResearchContract_(contract, inboxTitle, message) {
  const revisionId = String(
    contract.external_revision_id || contract.external_update_id || "",
  ).trim();
  const raw = JSON.stringify(contract);
  const chunks = [];
  for (let index = 0; index < raw.length; index += SYNC_CHUNK_CHARACTERS)
    chunks.push(raw.slice(index, index + SYNC_CHUNK_CHARACTERS));
  if (chunks.length > 100)
    throw new Error(
      "The contract is too large for the application sync inbox.",
    );

  const book = SpreadsheetApp.getActive();
  let inbox = book.getSheetByName(inboxTitle);
  if (!inbox) inbox = book.insertSheet(inboxTitle);
  const header = inbox
    .getRange(1, 1, 1, SYNC_INBOX_HEADERS.length)
    .getDisplayValues()[0];
  if (header.every((cell) => !String(cell).trim())) {
    inbox
      .getRange(1, 1, 1, SYNC_INBOX_HEADERS.length)
      .setValues([SYNC_INBOX_HEADERS]);
    inbox.setFrozenRows(1);
  } else if (
    SYNC_INBOX_HEADERS.some((value, index) => header[index] !== value)
  ) {
    throw new Error(
      `${inboxTitle} header does not match the application contract format.`,
    );
  }

  const lastRow = inbox.getLastRow();
  if (lastRow > 1) {
    const existing = inbox
      .getRange(2, 1, lastRow - 1, SYNC_INBOX_HEADERS.length)
      .getDisplayValues();
    const matching = existing.filter((row) => row[1] === revisionId);
    if (matching.length) {
      const ordered = matching
        .slice()
        .sort((left, right) => Number(left[2]) - Number(right[2]));
      const priorRaw = ordered.map((row) => row[4]).join("");
      const expectedCount = Number(ordered[0][3]);
      if (
        expectedCount === ordered.length &&
        ordered.every((row, index) => Number(row[2]) === index + 1) &&
        priorRaw === raw
      ) {
        SpreadsheetApp.getUi().alert(
          "This exact revision is already in the application inbox.",
        );
        return;
      }
      throw new Error(
        "This external revision ID already has different or incomplete inbox content. Use a new revision ID.",
      );
    }
  }

  const startRow = Math.max(2, lastRow + 1);
  const endRow = startRow + chunks.length - 1;
  if (endRow > SYNC_INBOX_MAX_ROWS + 1)
    throw new Error(`${inboxTitle} reached its 5,000-row limit.`);
  if (endRow > inbox.getMaxRows())
    inbox.insertRowsAfter(inbox.getMaxRows(), endRow - inbox.getMaxRows());
  const publishId = Utilities.getUuid();
  const values = chunks.map((chunk, index) => [
    publishId,
    revisionId,
    String(index + 1),
    String(chunks.length),
    chunk,
  ]);
  inbox
    .getRange(startRow, 1, values.length, SYNC_INBOX_HEADERS.length)
    .setNumberFormat("@");
  inbox
    .getRange(startRow, 1, values.length, SYNC_INBOX_HEADERS.length)
    .setValues(values);
  SpreadsheetApp.getUi().alert(message);
}

function assertRiskAssessmentContract_(contract) {
  if (!contract || typeof contract !== "object")
    throw new Error("The risk-assessment JSON must be one object.");
  const required = [
    "portfolio_id",
    "stream_key",
    "external_revision_id",
    "author_id",
    "source_id",
    "source_reference",
    "authored_at",
    "published_at",
    "portfolio_state_contract_version",
    "portfolio_state_fingerprint",
    "holdings_snapshot_id",
    "valuation_as_of",
    "coverage_status",
    "summary",
    "rationale",
  ];
  if (
    contract.contract_type !== "RiskAssessmentContractV1" ||
    contract.contract_version !== "1.0.0" ||
    required.some((key) => !String(contract[key] || "").trim()) ||
    contract.portfolio_state_contract_version !== "1.0.0" ||
    !Array.isArray(contract.findings)
  )
    throw new Error(
      "The contract must follow RiskAssessmentContractV1 1.0.0 and identify its exact portfolio baseline.",
    );
  const keys = contract.findings.map((finding) =>
    String(finding.finding_key || ""),
  );
  if (keys.some((key) => !key) || new Set(keys).size !== keys.length)
    throw new Error("Every risk finding needs a unique finding_key.");
}

function loadContractJson() {
  const html = HtmlService.createHtmlOutput(
    '<!doctype html><html><head><base target="_top"><style>' +
      "body{font:14px Arial,sans-serif;padding:16px}textarea{box-sizing:border-box;width:100%;height:350px;font:12px monospace}" +
      "button{margin-top:12px;padding:8px 14px}#error{color:#b3261e;white-space:pre-wrap}" +
      "</style></head><body><p>Paste the exported JSON contract below.</p>" +
      '<textarea id="contract" autofocus></textarea><div id="error"></div>' +
      '<button onclick="save()">Load contract</button><script>' +
      'function save(){const raw=document.getElementById("contract").value;' +
      "google.script.run.withSuccessHandler(()=>google.script.host.close())" +
      '.withFailureHandler(e=>document.getElementById("error").textContent=e.message)' +
      ".storeContractJson(raw);}" +
      "</script></body></html>",
  )
    .setWidth(640)
    .setHeight(480);
  SpreadsheetApp.getUi().showModalDialog(html, "Load model contract");
}

function storeContractJson(raw) {
  const contract = JSON.parse(raw);
  assertContract_(contract);
  if (
    !contract.candidate_revision ||
    !contract.model ||
    !contract.base_revision
  )
    throw new Error("The portable model contract is incomplete.");
  const book = SpreadsheetApp.getActive();
  let sheet = book.getSheetByName(CONTRACT_SHEET);
  if (!sheet) sheet = book.insertSheet(CONTRACT_SHEET);
  sheet.clearContents();
  sheet.getRange("A1").setNumberFormat("@");
  sheet.getRange("A1").setValue(JSON.stringify(contract));
}

function buildInputTabs() {
  const contract = readContract_();
  if (["2.0.0", "2.1.0"].includes(contract.contract_version)) {
    buildAdditionalInputTabs_(contract);
    return;
  }
  const candidate = contract.candidate_revision;
  writeTable_(
    "Base Inputs",
    ["field", "value"],
    Object.keys(candidate.base).map((key) => [
      key,
      String(candidate.base[key]),
    ]),
  );

  writeTable_(
    "Scenario Inputs",
    [
      "scenario",
      "probability",
      "terminal_growth",
      "year10_ufcf_growth",
      "rationale",
    ],
    candidate.scenarios.map((item) => [
      item.scenario,
      String(item.probability),
      String(item.terminal_growth),
      String(item.year10_ufcf_growth),
      item.rationale,
    ]),
  );

  const yearHeaders = [
    "scenario",
    "forecast_year",
    "revenue_growth",
    "ebit_margin",
    "tax_rate",
    "da_to_revenue",
    "capex_to_revenue",
    "nwc_to_revenue",
    "discount_rate",
  ];
  const yearRows = candidate.scenarios.flatMap((scenario) =>
    scenario.years.map((year) => [
      scenario.scenario,
      String(year.forecast_year),
      String(year.revenue_growth),
      String(year.ebit_margin),
      String(year.tax_rate),
      String(year.da_to_revenue),
      String(year.capex_to_revenue),
      String(year.nwc_to_revenue),
      String(year.discount_rate),
    ]),
  );
  writeTable_("Year Inputs", yearHeaders, yearRows);

  const tailRows = candidate.scenarios.flatMap((scenario) =>
    Array.from({ length: 5 }, (_, index) => {
      const forecastYear = index + 6;
      const input = scenario.tail_ufcf_growth?.find(
        (item) => Number(item.forecast_year) === forecastYear,
      );
      return [
        scenario.scenario,
        String(forecastYear),
        input ? String(input.ufcf_growth) : "",
      ];
    }),
  );
  writeTable_(
    "Tail Growth Inputs",
    ["scenario", "forecast_year", "ufcf_growth"],
    tailRows,
  );

  writeTable_(
    "Revision",
    ["field", "value"],
    [
      ["source_revision_id", candidate.source_revision_id],
      ["actor (fixed)", "IMPORT"],
      ["source", candidate.source || "Google Sheets portable contract"],
      ["rationale", candidate.rationale],
      ["effective_at", candidate.effective_at],
    ],
  );
  SpreadsheetApp.getActive().setActiveSheet(
    SpreadsheetApp.getActive().getSheetByName("Base Inputs"),
  );
  SpreadsheetApp.getUi().alert(
    "Editable input tabs are ready. Keep decimal values as text; the app validates ranges and recalculates outputs on import.",
  );
}

function writeEditsToContract() {
  const contract = readContract_();
  if (["2.0.0", "2.1.0"].includes(contract.contract_version)) {
    writeAdditionalEdits_(contract);
    return;
  }
  const candidate = contract.candidate_revision;
  const base = readKeyValues_("Base Inputs");
  Object.keys(candidate.base).forEach((key) => {
    candidate.base[key] = decimalText_(base[key], "Base Inputs: " + key);
  });

  const scenarioRows = readRows_("Scenario Inputs");
  if (scenarioRows.length !== 3)
    throw new Error("Expected exactly three scenario rows.");
  const scenariosByName = Object.fromEntries(
    candidate.scenarios.map((scenario) => [scenario.scenario, scenario]),
  );
  scenarioRows.forEach((row) => {
    const scenario = scenariosByName[row.scenario];
    if (!scenario) throw new Error("Unknown scenario: " + row.scenario);
    scenario.probability = decimalText_(
      row.probability,
      row.scenario + " probability",
    );
    scenario.terminal_growth = decimalText_(
      row.terminal_growth,
      row.scenario + " terminal growth",
    );
    scenario.year10_ufcf_growth = decimalText_(
      row.year10_ufcf_growth,
      row.scenario + " Year 10 growth",
    );
    scenario.rationale = requiredText_(
      row.rationale,
      row.scenario + " rationale",
    );
  });

  const yearRows = readRows_("Year Inputs");
  if (yearRows.length !== 15)
    throw new Error("Expected exactly 15 scenario/year rows.");
  const yearLookup = new Map();
  candidate.scenarios.forEach((scenario) =>
    scenario.years.forEach((year) =>
      yearLookup.set(scenario.scenario + ":" + year.forecast_year, year),
    ),
  );
  yearRows.forEach((row) => {
    const key = row.scenario + ":" + String(row.forecast_year);
    const year = yearLookup.get(key);
    if (!year) throw new Error("Unknown scenario/year row: " + key);
    Object.keys(year).forEach((field) => {
      if (field !== "forecast_year")
        year[field] = decimalText_(row[field], key + " " + field);
    });
  });

  const tailRows = readRows_("Tail Growth Inputs");
  if (tailRows.length !== 15)
    throw new Error("Expected exactly 15 Year 6–10 UFCF tail rows.");
  const tailValues = tailRows.map((row, index) => {
    const expectedScenario = ["BEAR", "BASE", "BULL"][Math.floor(index / 5)];
    const expectedYear = (index % 5) + 6;
    if (
      row.scenario !== expectedScenario ||
      Number(row.forecast_year) !== expectedYear
    )
      throw new Error(
        "Tail growth rows must remain in Bear/Base/Bull, Year 6–10 order.",
      );
    return String(row.ufcf_growth || "").trim();
  });
  const filledTailCount = tailValues.filter(Boolean).length;
  if (filledTailCount !== 0 && filledTailCount !== 15)
    throw new Error(
      "Fill all 15 explicit tail rates or leave all blank for linear fade.",
    );
  if (filledTailCount === 0) {
    candidate.scenarios.forEach((scenario) => {
      scenario.tail_ufcf_growth = null;
    });
  } else {
    candidate.scenarios.forEach((scenario, scenarioIndex) => {
      scenario.tail_ufcf_growth = Array.from({ length: 5 }, (_, index) => ({
        forecast_year: index + 6,
        ufcf_growth: decimalText_(
          tailValues[scenarioIndex * 5 + index],
          scenario.scenario + " Year " + (index + 6) + " UFCF growth",
        ),
      }));
    });
  }

  const revision = readKeyValues_("Revision");
  candidate.source_revision_id = requiredText_(
    revision.source_revision_id,
    "Revision source_revision_id",
  );
  candidate.actor = "IMPORT";
  candidate.source = requiredText_(revision.source, "Revision source");
  candidate.rationale = requiredText_(revision.rationale, "Revision rationale");
  candidate.effective_at = requiredText_(
    revision.effective_at,
    "Revision effective_at",
  );

  const sheet = SpreadsheetApp.getActive().getSheetByName(CONTRACT_SHEET);
  sheet.getRange("A1").setNumberFormat("@");
  sheet.getRange("A1").setValue(JSON.stringify(contract, null, 2));
  SpreadsheetApp.getUi().alert(
    "Contract JSON updated in Contract!A1. Copy it to a .json file and use Preview edited contract in the application.",
  );
}

function readContract_(requirePublishedEvidence = false) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(CONTRACT_SHEET);
  if (!sheet)
    throw new Error(
      "Create a sheet named Contract and paste exported JSON in A1.",
    );
  const raw = sheet.getRange("A1").getDisplayValue();
  const contract = JSON.parse(raw);
  assertContract_(contract, requirePublishedEvidence);
  return contract;
}

function assertContract_(contract, requirePublishedEvidence = false) {
  if (["1.0.0", "1.1.0", "1.2.0"].includes(contract.contract_version)) {
    if (
      !contract.candidate_revision ||
      !contract.model ||
      !contract.base_revision
    )
      throw new Error("The v1 portable model contract is incomplete.");
    if (requirePublishedEvidence && contract.contract_version === "1.2.0")
      assertProposalEvidence_(contract);
    return;
  }
  if (["2.0.0", "2.1.0"].includes(contract.contract_version)) {
    const candidate = contract.candidate_revision;
    if (
      !contract.model_id ||
      !contract.base_revision_id ||
      !candidate ||
      !candidate.source_revision_id ||
      candidate.actor !== "IMPORT" ||
      !candidate.effective_at ||
      (contract.model_type === "OWNER_CASH_FLOW_10Y" &&
        (!candidate.owner_cash_flow || candidate.residual_income != null)) ||
      (contract.model_type === "RESIDUAL_INCOME_10Y_FADE" &&
        (!candidate.residual_income || candidate.owner_cash_flow != null)) ||
      !["OWNER_CASH_FLOW_10Y", "RESIDUAL_INCOME_10Y_FADE"].includes(
        contract.model_type,
      )
    )
      throw new Error("The v2 method-specific model contract is incomplete.");
    if (requirePublishedEvidence && contract.contract_version === "2.1.0")
      assertProposalEvidence_(contract);
    return;
  }
  throw new Error("Unsupported portable model contract version.");
}

function assertProposalEvidence_(contract) {
  const proposal = contract.proposal;
  const evidence = contract.supporting_evidence;
  if (
    !proposal ||
    !proposal.author_id ||
    !proposal.authored_at ||
    !/^https:\/\//.test(String(proposal.source_reference || "")) ||
    !Array.isArray(evidence) ||
    evidence.length === 0
  )
    throw new Error(
      "Model contract v1.2.0/v2.1.0 requires proposal provenance and at least one published research or thesis reference.",
    );
  const seen = new Set();
  evidence.forEach((item) => {
    const allowed = [
      "RESEARCH_REVISION",
      "RESEARCH_FORECAST",
      "THESIS_REVISION",
      "THESIS_CLAIM",
    ];
    const key = `${item.evidence_type}:${item.reference_id}`;
    if (
      !allowed.includes(item.evidence_type) ||
      !item.reference_id ||
      !["SUPPORTS", "CONTRADICTS", "CONTEXT"].includes(item.relationship) ||
      seen.has(key)
    )
      throw new Error(
        "Model contract contains an invalid or repeated evidence reference.",
      );
    seen.add(key);
  });
}

function buildAdditionalInputTabs_(contract) {
  const candidate = contract.candidate_revision;
  const isOwner = contract.model_type === "OWNER_CASH_FLOW_10Y";
  const input = isOwner ? candidate.owner_cash_flow : candidate.residual_income;
  writeTable_(
    "Base Inputs",
    ["field", "value"],
    Object.keys(input.base).map((key) => [key, String(input.base[key])]),
  );

  const scenarioFields = isOwner
    ? ["probability", "required_return", "terminal_growth"]
    : [
        "probability",
        "starting_roe",
        "cost_of_equity",
        "terminal_growth",
        "mature_roe",
      ];
  writeTable_(
    "Scenario Inputs",
    ["scenario", ...scenarioFields, "rationale"],
    input.scenarios.map((item) => [
      item.scenario,
      ...scenarioFields.map((field) => String(item[field])),
      item.rationale,
    ]),
  );

  if (isOwner) {
    writeTable_(
      "Year Inputs",
      ["scenario", "forecast_year", "revenue_growth", "owner_cash_flow_margin"],
      input.scenarios.flatMap((scenario) =>
        scenario.years.map((year) => [
          scenario.scenario,
          String(year.forecast_year),
          String(year.revenue_growth),
          String(year.owner_cash_flow_margin),
        ]),
      ),
    );
  }
  writeRevisionTab_(candidate);
  SpreadsheetApp.getActive().setActiveSheet(
    SpreadsheetApp.getActive().getSheetByName("Base Inputs"),
  );
  SpreadsheetApp.getUi().alert(
    "Editable method-specific input tabs are ready. Keep decimal values as text; the application validates ranges and recalculates outputs on import.",
  );
}

function writeAdditionalEdits_(contract) {
  const candidate = contract.candidate_revision;
  const isOwner = contract.model_type === "OWNER_CASH_FLOW_10Y";
  const input = isOwner ? candidate.owner_cash_flow : candidate.residual_income;
  const baseRows = readRows_("Base Inputs");
  const base = Object.fromEntries(
    baseRows.map((row) => [row.field, row.value]),
  );
  Object.keys(input.base).forEach((key) => {
    input.base[key] = decimalText_(base[key], "Base Inputs: " + key);
  });

  const scenarioFields = isOwner
    ? ["probability", "required_return", "terminal_growth"]
    : [
        "probability",
        "starting_roe",
        "cost_of_equity",
        "terminal_growth",
        "mature_roe",
      ];
  const scenarioRows = readRows_("Scenario Inputs");
  if (scenarioRows.length !== 3)
    throw new Error("Expected exactly three scenario rows.");
  const scenarios = Object.fromEntries(
    input.scenarios.map((item) => [item.scenario, item]),
  );
  scenarioRows.forEach((row) => {
    const item = scenarios[row.scenario];
    if (!item) throw new Error("Unknown scenario: " + row.scenario);
    scenarioFields.forEach((field) => {
      item[field] = decimalText_(row[field], row.scenario + " " + field);
    });
    item.rationale = requiredText_(row.rationale, row.scenario + " rationale");
  });

  if (isOwner) {
    const yearRows = readRows_("Year Inputs");
    if (yearRows.length !== 30)
      throw new Error("Expected exactly 30 scenario/year rows.");
    const years = new Map();
    input.scenarios.forEach((scenario) =>
      scenario.years.forEach((year) =>
        years.set(scenario.scenario + ":" + year.forecast_year, year),
      ),
    );
    yearRows.forEach((row) => {
      const key = row.scenario + ":" + String(row.forecast_year);
      const year = years.get(key);
      if (!year) throw new Error("Unknown scenario/year row: " + key);
      year.revenue_growth = decimalText_(
        row.revenue_growth,
        key + " revenue_growth",
      );
      year.owner_cash_flow_margin = decimalText_(
        row.owner_cash_flow_margin,
        key + " owner_cash_flow_margin",
      );
    });
  }

  const revision = readKeyValues_("Revision");
  candidate.source_revision_id = requiredText_(
    revision.source_revision_id,
    "Revision source_revision_id",
  );
  candidate.actor = "IMPORT";
  candidate.source = requiredText_(revision.source, "Revision source");
  candidate.rationale = requiredText_(revision.rationale, "Revision rationale");
  candidate.effective_at = requiredText_(
    revision.effective_at,
    "Revision effective_at",
  );
  writeContractJson_(contract);
  SpreadsheetApp.getUi().alert(
    "Contract JSON updated in Contract!A1. Copy it to a .json file and use Preview edited contract in the application.",
  );
}

function writeRevisionTab_(candidate) {
  writeTable_(
    "Revision",
    ["field", "value"],
    [
      ["source_revision_id", candidate.source_revision_id],
      ["actor (fixed)", "IMPORT"],
      ["source", candidate.source || "Google Sheets portable contract v2"],
      ["rationale", candidate.rationale || ""],
      ["effective_at", candidate.effective_at],
    ],
  );
}

function writeContractJson_(contract) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(CONTRACT_SHEET);
  sheet.getRange("A1").setNumberFormat("@");
  sheet.getRange("A1").setValue(JSON.stringify(contract, null, 2));
}

function writeTable_(name, headers, rows) {
  const book = SpreadsheetApp.getActive();
  let sheet = book.getSheetByName(name);
  if (!sheet) sheet = book.insertSheet(name);
  sheet.clearContents();
  const values = [headers, ...rows].map((row) =>
    row.map((cell) => String(cell)),
  );
  sheet.getRange(1, 1, values.length, headers.length).setNumberFormat("@");
  sheet.getRange(1, 1, values.length, headers.length).setValues(values);
  sheet.setFrozenRows(1);
  sheet.autoResizeColumns(1, headers.length);
}

function readKeyValues_(sheetName) {
  const rows = readRows_(sheetName);
  return Object.fromEntries(rows.map((row) => [row.field, row.value]));
}

function readRows_(sheetName) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(sheetName);
  if (!sheet) throw new Error("Missing sheet: " + sheetName);
  const values = sheet.getDataRange().getDisplayValues();
  if (values.length < 2) return [];
  const headers = values[0];
  return values
    .slice(1)
    .filter((row) => row.some((cell) => cell !== ""))
    .map((row) =>
      Object.fromEntries(
        headers.map((header, index) => [header, row[index] || ""]),
      ),
    );
}

function decimalText_(value, label) {
  const text = requiredText_(value, label);
  if (!/^-?\d+(?:\.\d+)?$/.test(text))
    throw new Error(label + " must be a decimal written as text.");
  return text;
}

function requiredText_(value, label) {
  const text = String(value || "").trim();
  if (!text) throw new Error(label + " is required.");
  return text;
}
