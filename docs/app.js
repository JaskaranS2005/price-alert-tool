(() => {
  const form = document.querySelector('#upload-form');
  const messages = document.querySelector('#messages');
  const results = document.querySelector('.results');
  const body = document.querySelector('#alerts');
  const summary = document.querySelector('#summary');
  const instrumentFilter = document.querySelector('#instrument-filter');
  const ruleFilter = document.querySelector('#rule-filter');
  let alerts = [];

  const clean = value => String(value ?? '').trim();
  const validDate = value => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const [year, month, day] = value.split('-').map(Number);
    const candidate = new Date(Date.UTC(year, month - 1, day));
    return candidate.getUTCFullYear() === year && candidate.getUTCMonth() === month - 1 && candidate.getUTCDate() === day;
  };
  const tell = list => {
    messages.hidden = !list.length;
    messages.replaceChildren();
    if (list.length) { const ul = document.createElement('ul'); list.forEach(note => { const li = document.createElement('li'); li.textContent = note; ul.append(li); }); messages.append(ul); }
  };
  function csv(text) {
    const rows = []; let row = []; let value = ''; let quoted = false;
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      if (char === '"') { if (quoted && text[i + 1] === '"') { value += '"'; i += 1; } else quoted = !quoted; }
      else if (char === ',' && !quoted) { row.push(value); value = ''; }
      else if ((char === '\n' || char === '\r') && !quoted) { if (char === '\r' && text[i + 1] === '\n') i += 1; row.push(value); if (row.some(cell => clean(cell))) rows.push(row); row = []; value = ''; }
      else value += char;
    }
    if (quoted) throw new Error('The CSV has an unclosed quoted value.');
    row.push(value); if (row.some(cell => clean(cell))) rows.push(row);
    return rows;
  }
  function decimal(text) {
    const match = clean(text).match(/^([+-]?)(\d+)(?:\.(\d+))?$/);
    if (!match) throw new Error('not a finite decimal');
    const digits = match[3] || '';
    return { raw: clean(text), sign: match[1] === '-' ? -1n : 1n, units: BigInt(match[2] + digits), scale: digits.length };
  }
  const scaled = (number, scale) => number.sign * number.units * (10n ** BigInt(scale - number.scale));
  function pricesFrom(text, notes) {
    const rows = csv(text.replace(/^\uFEFF/, ''));
    if (!rows.length) return new Map();
    if (rows.length > 200_001) throw new Error('The prices file exceeds the 200,000-row limit.');
    const columns = rows.shift().map(cell => clean(cell).toLowerCase());
    const needed = ['date', 'instrument', 'close'];
    if (needed.some(name => !columns.includes(name))) throw new Error(`The prices file needs ${needed.join(', ')} columns.`);
    const positions = Object.fromEntries(columns.map((name, i) => [name, i])); const deduped = new Map(); let skipped = 0;
    rows.forEach((row, index) => {
      try {
        const day = clean(row[positions.date]); const instrument = clean(row[positions.instrument]).toUpperCase(); const close = decimal(row[positions.close]);
        if (!validDate(day) || !instrument || instrument.length > 80 || close.sign < 0n || close.units === 0n) throw new Error();
        const key = `${instrument}\u0000${day}`; if (deduped.has(key)) notes.push(`Duplicate ${instrument} price on ${day}: the final row was kept.`);
        deduped.set(key, { day, instrument, close });
      } catch { skipped += 1; notes.push(`Skipped malformed price row ${index + 2}.`); }
    });
    if (skipped) notes.push(`${skipped} malformed price row${skipped === 1 ? '' : 's'} skipped.`);
    const grouped = new Map(); deduped.forEach(item => { if (!grouped.has(item.instrument)) grouped.set(item.instrument, []); grouped.get(item.instrument).push(item); });
    grouped.forEach(items => items.sort((a, b) => a.day.localeCompare(b.day)));
    return grouped;
  }
  function rulesFrom(text, notes) {
    let raw; try { raw = JSON.parse(text.replace(/^\uFEFF/, '')); } catch { throw new Error('The rules file is not valid JSON.'); }
    if (!Array.isArray(raw)) throw new Error('Rules JSON must contain a list.');
    if (raw.length > 200) throw new Error('The rules file exceeds the 200-rule limit.');
    const ids = new Set(); const rules = [];
    raw.forEach((item, index) => {
      try {
        const id = clean(item.id); const instrument = clean(item.instrument).toUpperCase(); const type = clean(item.type); const direction = clean(item.direction).toLowerCase();
        if (!id || id.length > 80 || !instrument || instrument.length > 80 || ids.has(id) || !['above', 'below'].includes(direction)) throw new Error();
        if (type === 'level') { const level = decimal(item.level); if (level.sign < 0n || level.units === 0n) throw new Error(); rules.push({ id, instrument, type, direction, level }); }
        else if (type === 'ma_cross' && Number.isInteger(item.short) && Number.isInteger(item.long) && item.short > 0 && item.long > item.short) rules.push({ id, instrument, type, direction, short:item.short, long:item.long });
        else throw new Error(); ids.add(id);
      } catch { notes.push(`Invalid rule ${index + 1} was skipped.`); }
    }); return rules;
  }
  function evaluate(grouped, rules, notes) {
    const answer = [];
    for (const rule of rules) {
      const series = grouped.get(rule.instrument); if (!series) { notes.push(`Rule “${rule.id}” has no data for ${rule.instrument}.`); continue; }
      const scale = Math.max(...series.map(item => item.close.scale), rule.type === 'level' ? rule.level.scale : 0);
      const values = series.map(item => scaled(item.close, scale));
      if (rule.type === 'level') {
        const level = scaled(rule.level, scale);
        for (let i = 1; i < series.length; i += 1) { const crossed = rule.direction === 'above' ? values[i-1] <= level && values[i] > level : values[i-1] >= level && values[i] < level; if (crossed) answer.push({ day:series[i].day, id:rule.id, instrument:rule.instrument, event:`level ${rule.direction} ${rule.level.raw}` }); }
      } else {
        const sma = window => { let total = 0n; return values.map((value, i) => { total += value; if (i >= window) total -= values[i-window]; return i >= window - 1 ? total : null; }); };
        const short = sma(rule.short), long = sma(rule.long);
        for (let i = 1; i < series.length; i += 1) { if ([short[i-1], long[i-1], short[i], long[i]].some(value => value === null)) continue; const previous = short[i-1] * BigInt(rule.long) - long[i-1] * BigInt(rule.short); const current = short[i] * BigInt(rule.long) - long[i] * BigInt(rule.short); const crossed = rule.direction === 'above' ? previous <= 0n && current > 0n : previous >= 0n && current < 0n; if (crossed) answer.push({ day:series[i].day, id:rule.id, instrument:rule.instrument, event:`ma_cross ${rule.short}/${rule.long} ${rule.direction}` }); }
      }
    }
    return answer.sort((a,b) => a.day.localeCompare(b.day) || a.id.localeCompare(b.id));
  }
  function options(select, values, label) { select.replaceChildren(new Option(label, '')); [...values].sort().forEach(value => select.append(new Option(value, value))); }
  function render() { const instrument = instrumentFilter.value; const rule = ruleFilter.value; const shown = alerts.filter(item => (!instrument || item.instrument === instrument) && (!rule || item.id === rule)); body.replaceChildren(); shown.forEach(item => { const row = document.createElement('tr'); [item.day,item.id,item.instrument,item.event].forEach(text => { const cell = document.createElement('td'); cell.textContent = text; row.append(cell); }); body.append(row); }); summary.textContent = shown.length ? `${shown.length} alert${shown.length === 1 ? '' : 's'} shown.` : 'No alerts match these filters.'; }
  form.addEventListener('submit', async event => { event.preventDefault(); tell([]); const prices = document.querySelector('#prices').files[0], rules = document.querySelector('#rules').files[0]; if (!prices || !rules) { tell(['Choose both files before evaluating.']); return; } if (prices.size > 2_000_000 || rules.size > 2_000_000) { tell(['Each file must be smaller than 2 MB.']); return; }
    const notes = []; try { const [priceText, ruleText] = await Promise.all([prices.text(), rules.text()]); alerts = evaluate(pricesFrom(priceText, notes), rulesFrom(ruleText, notes), notes); options(instrumentFilter, new Set(alerts.map(item => item.instrument)), 'All instruments'); options(ruleFilter, new Set(alerts.map(item => item.id)), 'All rules'); results.hidden = false; render(); tell(notes); } catch (error) { results.hidden = true; tell([error.message || 'Could not evaluate these files.']); }
  });
  instrumentFilter.addEventListener('change', render); ruleFilter.addEventListener('change', render);
  document.querySelector('#export').addEventListener('click', () => { const content = ['date,rule_id,instrument,event', ...alerts.map(item => [item.day,item.id,item.instrument,item.event].map(value => `"${value.replaceAll('"','""')}"`).join(','))].join('\n'); const url = URL.createObjectURL(new Blob([content], {type:'text/csv'})); const a = Object.assign(document.createElement('a'), {href:url, download:'price-alerts.csv'}); a.click(); URL.revokeObjectURL(url); });
})();
