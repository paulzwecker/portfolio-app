/**
 * Human-reviewed Google Sheets adapter for FinancialModelContractV1 and V2.
 * This script reads/writes portable JSON locally in the active spreadsheet; it
 * never calls the portfolio API and never recalculates model outputs.
 */
const CONTRACT_SHEET = "Contract";

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Portfolio model")
    .addItem("Load exported contract JSON", "loadContractJson")
    .addItem("Build editable input tabs", "buildInputTabs")
    .addItem("Write edits back to contract JSON", "writeEditsToContract")
    .addToUi();
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
  if (contract.contract_version === "2.0.0") {
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
  if (contract.contract_version === "2.0.0") {
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

function readContract_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(CONTRACT_SHEET);
  if (!sheet)
    throw new Error(
      "Create a sheet named Contract and paste exported JSON in A1.",
    );
  const raw = sheet.getRange("A1").getDisplayValue();
  const contract = JSON.parse(raw);
  assertContract_(contract);
  return contract;
}

function assertContract_(contract) {
  if (contract.contract_version === "1.0.0") {
    if (
      !contract.candidate_revision ||
      !contract.model ||
      !contract.base_revision
    )
      throw new Error("The v1 portable model contract is incomplete.");
    return;
  }
  if (contract.contract_version === "2.0.0") {
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
    return;
  }
  throw new Error(
    "Only portable model contract versions 1.0.0 and 2.0.0 are supported.",
  );
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
