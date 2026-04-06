const SHEET_NAMES = {
    publications: 'publications',
    sdgExploded: 'sdg_exploded',
    kpisYearly: 'kpis_yearly',
    refreshLog: 'refresh_log',
};
const LOCK_TIMEOUT_MS = 30000;
const TEMP_SHEET_PREFIX = '__tmp__ods_ulpgc__';
const NUMERIC_COLUMNS_BY_SHEET = {
    publications: [
        'publication_year',
        'cited_by_count',
        'countries_distinct_count',
        'institutions_distinct_count',
        'fwci',
        'citation_normalized_percentile_value',
        'sdg_count',
    ],
    sdg_exploded: ['publication_year', 'score'],
    kpis_yearly: [
        'publication_year',
        'total_publications',
        'total_oa_publications',
        'oa_share',
        'total_sdg_mentions',
        'publications_with_sdg',
        'avg_citations',
    ],
    refresh_log: [
        'analysis_start_year',
        'analysis_end_year',
        'raw_record_count',
        'publications_row_count',
        'sdg_exploded_row_count',
        'kpis_yearly_row_count',
    ],
};

function onOpen() {
    SpreadsheetApp.getUi()
        .createMenu('ODS-ULPGC')
        .addItem('Refresh sheets from latest files in Drive', 'runManualRefreshFromDrive')
        .addToUi();
}

function doPost(e) {
    const lock = LockService.getScriptLock();
    try {
        lock.waitLock(LOCK_TIMEOUT_MS);

        const config = getConfig_();
        const payload = parsePayload_(e);

        validateSecret_(payload.secret, config.webhookSharedSecret);

        saveFilesToDrive_(payload, config);
        refreshSheetsFromPayload_(payload, config);
        SpreadsheetApp.flush();

        return jsonResponse_({
            status: 'ok',
            message: 'Drive and Sheets updated successfully.',
            snapshot_label: payload.snapshot_label,
        });
    } catch (error) {
        return jsonResponse_({
            status: 'error',
            message: String(error),
        });
    } finally {
        lock.releaseLock();
    }
}

function runManualRefreshFromDrive() {
    const lock = LockService.getScriptLock();
    try {
        lock.waitLock(LOCK_TIMEOUT_MS);

        const config = getConfig_();
        const spreadsheet = SpreadsheetApp.openById(config.spreadsheetId);

        const publicationsCsv = readTextFileByPath_(
            config.rootFolderId,
            ['01_data_processed', 'latest'],
            'publications_latest.csv'
        );

        const sdgExplodedCsv = readTextFileByPath_(
            config.rootFolderId,
            ['01_data_processed', 'latest'],
            'sdg_exploded_latest.csv'
        );

        const kpisYearlyCsv = readTextFileByPath_(
            config.rootFolderId,
            ['01_data_processed', 'latest'],
            'kpis_yearly_latest.csv'
        );

        const refreshLogCsv = readTextFileByPath_(
            config.rootFolderId,
            ['03_logs'],
            'refresh_log.csv'
        );

        replaceSheetsFromCsvMap_(spreadsheet, {
            [SHEET_NAMES.publications]: publicationsCsv,
            [SHEET_NAMES.sdgExploded]: sdgExplodedCsv,
            [SHEET_NAMES.kpisYearly]: kpisYearlyCsv,
            [SHEET_NAMES.refreshLog]: refreshLogCsv,
        });
        SpreadsheetApp.flush();
    } finally {
        lock.releaseLock();
    }
}

function getConfig_() {
    const props = PropertiesService.getScriptProperties();

    const rootFolderId = props.getProperty('ROOT_FOLDER_ID');
    const spreadsheetId = props.getProperty('SPREADSHEET_ID');
    const webhookSharedSecret = props.getProperty('WEBHOOK_SHARED_SECRET');

    if (!rootFolderId || !spreadsheetId || !webhookSharedSecret) {
        throw new Error(
            'Missing script properties. Required: ROOT_FOLDER_ID, SPREADSHEET_ID, WEBHOOK_SHARED_SECRET'
        );
    }

    return {
        rootFolderId,
        spreadsheetId,
        webhookSharedSecret,
    };
}

function parsePayload_(e) {
    if (!e || !e.postData || !e.postData.contents) {
        throw new Error('Empty POST body.');
    }

    const payload = JSON.parse(e.postData.contents);

    const requiredKeys = [
        'secret',
        'snapshot_date',
        'snapshot_label',
        'analysis_start_year',
        'analysis_end_year',
        'publications_csv_base64',
        'sdg_exploded_csv_base64',
        'kpis_yearly_csv_base64',
        'refresh_log_csv_base64',
        'metadata_json_base64',
    ];

    requiredKeys.forEach((key) => {
        if (!(key in payload)) {
            throw new Error(`Missing payload key: ${key}`);
        }
    });

    return payload;
}

function validateSecret_(receivedSecret, expectedSecret) {
    if (!receivedSecret || receivedSecret !== expectedSecret) {
        throw new Error('Unauthorized webhook request.');
    }
}

function saveFilesToDrive_(payload, config) {
    const archiveSuffix = buildArchiveSuffix_(
        payload.snapshot_date,
        payload.analysis_start_year,
        payload.analysis_end_year
    );

    const processedLatestFolder = getFolderByPath_(config.rootFolderId, ['01_data_processed', 'latest']);
    const processedArchiveFolder = getFolderByPath_(config.rootFolderId, ['01_data_processed', 'archive']);
    const docsFolder = getFolderByPath_(config.rootFolderId, ['02_docs']);
    const logsFolder = getFolderByPath_(config.rootFolderId, ['03_logs']);

    const publicationsCsv = decodeBase64ToText_(payload.publications_csv_base64);
    const sdgExplodedCsv = decodeBase64ToText_(payload.sdg_exploded_csv_base64);
    const kpisYearlyCsv = decodeBase64ToText_(payload.kpis_yearly_csv_base64);
    const refreshLogCsv = decodeBase64ToText_(payload.refresh_log_csv_base64);
    const metadataJson = decodeBase64ToText_(payload.metadata_json_base64);

    upsertTextFile_(processedLatestFolder, 'publications_latest.csv', publicationsCsv, MimeType.CSV);
    upsertTextFile_(processedLatestFolder, 'sdg_exploded_latest.csv', sdgExplodedCsv, MimeType.CSV);
    upsertTextFile_(processedLatestFolder, 'kpis_yearly_latest.csv', kpisYearlyCsv, MimeType.CSV);

    upsertTextFile_(
        processedArchiveFolder,
        `publications_${archiveSuffix}.csv`,
        publicationsCsv,
        MimeType.CSV
    );
    upsertTextFile_(
        processedArchiveFolder,
        `sdg_exploded_${archiveSuffix}.csv`,
        sdgExplodedCsv,
        MimeType.CSV
    );
    upsertTextFile_(
        processedArchiveFolder,
        `kpis_yearly_${archiveSuffix}.csv`,
        kpisYearlyCsv,
        MimeType.CSV
    );

    upsertTextFile_(logsFolder, 'refresh_log.csv', refreshLogCsv, MimeType.CSV);
    upsertTextFile_(docsFolder, 'latest_snapshot_metadata.json', metadataJson, MimeType.PLAIN_TEXT);
}

function refreshSheetsFromPayload_(payload, config) {
    const spreadsheet = SpreadsheetApp.openById(config.spreadsheetId);
    replaceSheetsFromCsvMap_(spreadsheet, {
        [SHEET_NAMES.publications]: decodeBase64ToText_(payload.publications_csv_base64),
        [SHEET_NAMES.sdgExploded]: decodeBase64ToText_(payload.sdg_exploded_csv_base64),
        [SHEET_NAMES.kpisYearly]: decodeBase64ToText_(payload.kpis_yearly_csv_base64),
        [SHEET_NAMES.refreshLog]: decodeBase64ToText_(payload.refresh_log_csv_base64),
    });
}

function replaceSheetsFromCsvMap_(spreadsheet, csvBySheetName) {
    const operationId = Utilities.getUuid().slice(0, 8);
    const plans = Object.keys(csvBySheetName).map((sheetName) => ({
        sheetName,
        csvText: csvBySheetName[sheetName],
        stagingName: buildTemporarySheetName_(sheetName, 'staging', operationId),
        backupName: buildTemporarySheetName_(sheetName, 'backup', operationId),
    }));

    const renamedTargets = [];
    const promotedTargets = [];

    try {
        plans.forEach((plan) => {
            const stagingSheet = spreadsheet.insertSheet(plan.stagingName);
            writeSheetFromCsv_(stagingSheet, plan.sheetName, plan.csvText);
            plan.stagingSheet = stagingSheet;
        });

        plans.forEach((plan) => {
            const currentSheet = spreadsheet.getSheetByName(plan.sheetName);
            if (currentSheet) {
                currentSheet.setName(plan.backupName);
                renamedTargets.push(plan);
            }

            plan.stagingSheet.setName(plan.sheetName);
            promotedTargets.push(plan);
        });

        SpreadsheetApp.flush();

        renamedTargets.forEach((plan) => {
            const backupSheet = spreadsheet.getSheetByName(plan.backupName);
            if (backupSheet) {
                spreadsheet.deleteSheet(backupSheet);
            }
        });
    } catch (error) {
        rollbackSheetReplacement_(spreadsheet, promotedTargets, renamedTargets);
        throw error;
    } finally {
        cleanupTemporarySheets_(spreadsheet, plans);
    }
}

function rollbackSheetReplacement_(spreadsheet, promotedTargets, renamedTargets) {
    promotedTargets
        .slice()
        .reverse()
        .forEach((plan) => {
            const promotedSheet = spreadsheet.getSheetByName(plan.sheetName);
            if (promotedSheet) {
                promotedSheet.setName(plan.stagingName);
            }
        });

    renamedTargets
        .slice()
        .reverse()
        .forEach((plan) => {
            const backupSheet = spreadsheet.getSheetByName(plan.backupName);
            if (backupSheet) {
                backupSheet.setName(plan.sheetName);
            }
        });
}

function cleanupTemporarySheets_(spreadsheet, plans) {
    plans.forEach((plan) => {
        deleteSheetIfExists_(spreadsheet, plan.stagingName);
        deleteSheetIfExists_(spreadsheet, plan.backupName);
    });
}

function deleteSheetIfExists_(spreadsheet, sheetName) {
    const sheet = spreadsheet.getSheetByName(sheetName);
    if (sheet) {
        spreadsheet.deleteSheet(sheet);
    }
}

function buildTemporarySheetName_(sheetName, kind, operationId) {
    return `${TEMP_SHEET_PREFIX}${kind}__${sheetName}__${operationId}`;
}

function writeSheetFromCsv_(sheet, sheetName, csvText) {
    const cleanText = stripBom_(csvText);
    const values = convertCsvValuesForSheet_(sheetName, Utilities.parseCsv(cleanText));

    if (!values || values.length === 0) {
        throw new Error(`CSV for sheet "${sheetName}" is empty.`);
    }

    sheet.clear();

    const numRows = values.length;
    const numCols = values[0].length;

    sheet.getRange(1, 1, numRows, numCols).setValues(values);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, numCols).setFontWeight('bold');
    sheet.autoResizeColumns(1, numCols);
}

function convertCsvValuesForSheet_(sheetName, values) {
    if (!values || values.length === 0) {
        return values;
    }

    const numericColumns = NUMERIC_COLUMNS_BY_SHEET[sheetName] || [];
    if (numericColumns.length === 0) {
        return values;
    }

    const header = values[0];
    const numericColumnIndexes = header.reduce((indexes, columnName, index) => {
        if (numericColumns.indexOf(columnName) !== -1) {
            indexes.push(index);
        }
        return indexes;
    }, []);

    if (numericColumnIndexes.length === 0) {
        return values;
    }

    const convertedRows = values.slice(1).map((row) =>
        row.map((cellValue, index) => {
            if (numericColumnIndexes.indexOf(index) === -1) {
                return cellValue;
            }

            if (cellValue === null || cellValue === undefined) {
                return '';
            }

            const trimmedValue = String(cellValue).trim();
            if (trimmedValue === '') {
                return '';
            }

            const numericValue = Number(trimmedValue);
            return Number.isFinite(numericValue) ? numericValue : cellValue;
        })
    );

    return [header].concat(convertedRows);
}

function getFolderByPath_(rootFolderId, pathParts) {
    let folder = DriveApp.getFolderById(rootFolderId);

    pathParts.forEach((part) => {
        const children = folder.getFoldersByName(part);
        if (!children.hasNext()) {
            throw new Error(`Subfolder not found: ${part}`);
        }
        folder = children.next();
    });

    return folder;
}

function readTextFileByPath_(rootFolderId, pathParts, fileName) {
    const folder = getFolderByPath_(rootFolderId, pathParts);
    const files = folder.getFilesByName(fileName);

    if (!files.hasNext()) {
        throw new Error(`File not found: ${fileName}`);
    }

    return files.next().getBlob().getDataAsString('UTF-8');
}

function listFilesByName_(folder, fileName) {
    const files = folder.getFilesByName(fileName);
    const matches = [];
    while (files.hasNext()) {
        matches.push(files.next());
    }
    return matches;
}

function upsertTextFile_(folder, fileName, content, mimeType) {
    const existing = listFilesByName_(folder, fileName);
    if (existing.length > 1) {
        throw new Error(`Multiple files found with name: ${fileName}`);
    }

    if (existing.length === 1) {
        existing[0].setContent(content);
        return existing[0];
    }

    return folder.createFile(fileName, content, mimeType);
}

function decodeBase64ToText_(base64String) {
    const bytes = Utilities.base64Decode(base64String);
    return Utilities.newBlob(bytes).getDataAsString('UTF-8');
}

function stripBom_(text) {
    if (!text) {
        return text;
    }
    return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

function buildArchiveSuffix_(snapshotDate, startYear, endYear) {
    const yearMonth = snapshotDate.slice(0, 7);
    return `${yearMonth}_window_${startYear}_${endYear}`;
}

function jsonResponse_(obj) {
    return ContentService
        .createTextOutput(JSON.stringify(obj))
        .setMimeType(ContentService.MimeType.JSON);
}
