/* Native SVG -> AI import/export. Only documents created here are closed. */
function exportScientificFigure(config) {
    function quote(value) {
        return '"' + String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')
            .replace(/\r/g, '\\r').replace(/\n/g, '\\n').replace(/\t/g, '\\t') + '"';
    }
    function encode(value) {
        if (value === null) return 'null';
        if (typeof value === 'string') return quote(value);
        if (typeof value === 'number' || typeof value === 'boolean') return String(value);
        var out = [], key, i;
        if (value instanceof Array) {
            for (i = 0; i < value.length; i++) out.push(encode(value[i]));
            return '[' + out.join(',') + ']';
        }
        for (key in value) if (value.hasOwnProperty(key)) out.push(quote(key) + ':' + encode(value[key]));
        return '{' + out.join(',') + '}';
    }
    function snapshot(doc) {
        var texts = [], fonts = [], i, j, name, frame;
        for (i = 0; i < doc.textFrames.length; i++) {
            frame = doc.textFrames[i];
            texts.push(frame.contents);
            for (j = 0; j < frame.characters.length; j++) {
                name = frame.characters[j].characterAttributes.textFont.name;
                if (('|' + fonts.join('|') + '|').indexOf('|' + name + '|') < 0) fonts.push(name);
            }
        }
        texts.sort(); fonts.sort();
        var result = {
            paths: doc.pathItems.length, compounds: doc.compoundPathItems.length,
            textFrames: doc.textFrames.length, rasterItems: doc.rasterItems.length,
            placedItems: doc.placedItems.length, texts: texts, fonts: fonts
        };
        if (result.rasterItems || result.placedItems) throw new Error('Raster or linked items detected after native import.');
        if (!result.paths) throw new Error('No editable native paths found.');
        if (config.expectedText > 0 && !result.textFrames) throw new Error('Editable text was lost.');
        function normalized(values) {
            var copy = [];
            for (var t = 0; t < values.length; t++) copy.push(values[t].replace(/\s/g, ''));
            copy.sort(); return copy;
        }
        var expected = normalized(config.sourceTexts), actual = normalized(texts);
        if (expected.join('').split('').sort().join('') !== actual.join('').split('').sort().join('')) {
            throw new Error('Source SVG and native text character inventories differ (whitespace excluded).');
        }
        result.sourceTextCount = config.expectedText;
        result.sourceCharactersMatch = true;
        result.exactTextGroupsMatch = encode(expected) === encode(actual);
        result.splitTextRequiresVisualReview = !result.exactTextGroupsMatch;
        return result;
    }
    var previousInteraction = app.userInteractionLevel;
    var stage = config.stage;
    try {
        var source = new File(config.svg), ai = new File(config.ai), png = new File(config.png);
        if (!source.exists) throw new Error('SVG does not exist.');
        if (stage === 'validate') {
            if (ai.exists || png.exists) throw new Error('Refusing to overwrite existing output.');
            for (var existing = 0; existing < app.documents.length; existing++) {
                var openedPath = '';
                try { openedPath = app.documents[existing].fullName.fsName; } catch (ignored) {}
                if (openedPath.toLowerCase() === source.fsName.toLowerCase()) {
                    throw new Error('Source SVG is already open. Copy it to a new task-local SVG path before exporting; existing document was not changed.');
                }
            }
            return 'OK|{}';
        }
        app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
        var doc = app.activeDocument;
        var expectedFile = stage === 'save' ? source : ai;
        if (doc.fullName.fsName.toLowerCase() !== expectedFile.fsName.toLowerCase()) {
            throw new Error('Active document changed; refusing to modify it.');
        }
        if (stage === 'save') {
            if (ai.exists) throw new Error('Refusing to overwrite AI.');
            var imported = snapshot(doc);
            var opts = new IllustratorSaveOptions();
            opts.pdfCompatible = true;
            opts.compressed = true;
            doc.saveAs(ai, opts);
            return 'OK|' + encode({imported: imported});
        }
        if (stage === 'close-created') {
            doc.close(SaveOptions.DONOTSAVECHANGES);
            return 'OK|{}';
        }
        if (stage !== 'verify-export') throw new Error('Unknown export stage.');
        var reopened = snapshot(doc);
        for (var key in config.imported) if (config.imported.hasOwnProperty(key)) {
            if (encode(config.imported[key]) !== encode(reopened[key])) {
                throw new Error('Native property changed after AI save/reopen: ' + key);
            }
        }
        var board = doc.artboards[0].artboardRect;
        var pngOpts = new ExportOptionsPNG24();
        pngOpts.antiAliasing = true;
        pngOpts.transparency = false;
        pngOpts.artBoardClipping = true;
        pngOpts.horizontalScale = config.dpi / 72 * 100;
        pngOpts.verticalScale = config.dpi / 72 * 100;
        if (png.exists) throw new Error('Refusing to overwrite PNG.');
        doc.exportFile(png, ExportType.PNG24, pngOpts);
        app.redraw();
        return 'OK|' + encode({
            version: app.version, imported: config.imported, reopened: reopened,
            widthPt: board[2] - board[0], heightPt: board[1] - board[3],
            aiReopened: true, currentDocument: doc.name
        });
    } catch (error) {
        return 'ERROR|' + stage + ': ' + error.message;
    } finally {
        app.userInteractionLevel = previousInteraction;
    }
}
