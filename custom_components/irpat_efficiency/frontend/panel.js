// Initial dependency-free custom element; local assets only.
// User-defined labels are inserted through textContent, not HTML.
class IrpatEfficiencyPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this.entries = [];
    this.error = false;
    this.loaded = false;
    this.busy = false;
    this.displayMode = 'heating';
    this.historyHours = '24';
    this.timer = null;
  }

  set hass(value) {
    this._hass = value;
    if (!this.loaded && !this.busy && this.isConnected && value) this.refresh();
  }

  connectedCallback() {
    this.render();
    if (this._hass && !this.busy) this.refresh();
    if (this.timer === null) this.timer = setInterval(() => { if (!document.hidden) this.refresh(true); }, 30000);
  }

  disconnectedCallback() {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }

  async refresh(quiet = false) {
    if (!this._hass || this.busy) return;
    this.busy = true;
    if (!quiet) this.render();
    try {
      this.entries = await this._hass.callWS({type:"irpat_efficiency/overview"});
      this.error = false;
    } catch (err) {
      this.entries = [];
      this.error = true;
    } finally {
      this.loaded = true;
      this.busy = false;
      if (this.isConnected) this.render();
    }
  }

  t(ro, en) { return (this._hass?.language || "").startsWith("ro") ? ro : en; }

  node(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = String(text);
    if (cls) e.className = cls;
    return e;
  }

  card(title, value) {
    const e = this.node("div", undefined, "card metric");
    e.append(this.node("div", title, "muted"), this.node("strong", value));
    return e;
  }

  render() {
    const root = this.shadowRoot;
    root.replaceChildren();
    const style = this.node("style");
    style.textContent = `
      :host{display:block;color:var(--primary-text-color);background:var(--primary-background-color);min-height:100%}
      main{padding:20px;max-width:1200px;margin:auto;box-sizing:border-box}
      header{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
      h1{font-size:1.5rem;flex:1;margin:0}h2{font-size:1.2rem}h3{font-size:1rem}
      .muted{color:var(--secondary-text-color)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:10px}
      .card{border:1px solid var(--divider-color);background:var(--card-background-color);border-radius:14px;padding:14px;margin-bottom:12px;box-sizing:border-box}
      .metric strong{font-size:1.7rem;display:block;margin-top:5px}
      button,a.action{background:var(--primary-color);color:var(--text-primary-color,#fff);border:0;border-radius:8px;padding:10px 14px;font:inherit;cursor:pointer;text-decoration:none}
      button:disabled{opacity:.6;cursor:default}button:focus-visible,a:focus-visible{outline:3px solid var(--primary-text-color)}
      .loops{overflow-x:auto;display:flex;gap:8px;padding:10px 4px 6px}
      .loop{flex:0 0 105px;min-width:0;text-align:center}
      .meter{width:20px;height:54px;border:2px solid #8796a5;border-radius:5px;margin:5px auto;background:repeating-linear-gradient(to bottom,transparent 0 8px,#8796a5 8px 9px)}
      .supply,.return{height:8px;border-radius:4px}.supply{background:#e57345}.return{background:#2196d3}
      .pipe{height:18px;width:4px;background:#8796a5;margin:auto}
      .status-within{color:var(--success-color,#22a06b)}.status-warm{color:var(--error-color,#e57345)}.status-cold{color:#2196d3}
      .history{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:6px;margin:8px 0 14px;padding:8px;border-radius:8px;background:var(--secondary-background-color)}.history small{display:block}.history select{font:inherit;color:var(--primary-text-color);background:var(--card-background-color)}
      .temperature{text-align:right;flex-shrink:0}.temperature strong{font-size:1.2rem}.temperature small{display:block}
      .mode{display:flex;gap:8px;margin:16px 0}.mode button[aria-pressed="false"]{background:var(--secondary-background-color);color:var(--primary-text-color)}
      .label{overflow-wrap:anywhere}.room{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid var(--divider-color)}
      @media(max-width:600px){main{padding:12px}}
    `;
    root.append(style);
    const main = this.node("main");
    const header = this.node("header");
    header.append(this.node("h1","irPaT & Eficiență"));
    const refresh = this.node("button",this.t("Actualizează","Refresh"));
    refresh.disabled = this.busy;
    refresh.addEventListener("click",()=>this.refresh());
    header.append(refresh);
    main.append(header);
    main.append(this.node("p",this.t("Prezentare generală · versiune experimentală","Overview · experimental version"),"muted"));
    const link = this.node("a",this.t("Configurează integrarea","Configure integration"),"action");
    link.href = "/config/integrations";
    main.append(link);
    const modes = this.node("div",undefined,"mode");
    for (const [key,ro,en] of [["heating","Încălzire","Heating"],["cooling","Răcire","Cooling"]]) {
      const button=this.node("button",this.t(ro,en));
      button.setAttribute("aria-pressed",String(this.displayMode===key));
      button.addEventListener("click",()=>{this.displayMode=key;this.render();});
      modes.append(button);
    }
    main.append(modes,this.node("p",this.t("Modul selectat schimbă doar ținta afișată, nu regimul instalației.","Selected mode changes only the displayed target, not the equipment mode."),"muted"));
    if (this.busy) main.append(this.node("p",this.t("Se încarcă…","Loading…")));
    if (this.error) main.append(this.node("p",this.t("Nu s-a putut încărca configurația. Încearcă din nou.","Could not load configuration. Try again.")));
    if (!this.busy && !this.error && !this.entries.length) main.append(this.node("p",this.t("Nu există o configurație activă.","No active configuration.")));
    for (const entry of this.entries) {
      const t = entry.topology;
      main.append(this.node("h2",entry.name));
      if(entry.history_save_failed) main.append(this.node("p",this.t("Istoricul nu a putut fi salvat pe disc.","History could not be saved to disk."),"status-warm"));
      const period=this.node("select");
      period.setAttribute("aria-label",this.t("Interval istoric","History interval"));
      for(const h of ["24","48","72","168"]){const option=this.node("option",h+" h");option.value=h;period.append(option);}
      period.value=this.historyHours;
      period.addEventListener("change",()=>{this.historyHours=period.value;this.render();});
      const periodLabel=this.node("label",this.t("Interval statistic: ","Statistics interval: "));periodLabel.append(period);main.append(periodLabel);
      const grid = this.node("div",undefined,"grid");
      for (const [key,ro,en] of [["floors","Niveluri","Floors"],["rooms","Încăperi","Rooms"],["manifolds","Distribuitoare","Manifolds"],["circuits","Circuite","Circuits"],["zones","Zone","Zones"],["sources","Surse","Sources"]])
        grid.append(this.card(this.t(ro,en),(t[key]||[]).length));
      main.append(grid);
      const rooms = new Map((t.rooms||[]).map(r=>[r.id,r]));
      for (const floor of t.floors||[]) {
        const section = this.node("section",undefined,"card");
        section.append(this.node("h2",floor.name));
        for (const room of (t.rooms||[]).filter(r=>r.floor_id===floor.id)) {
          const row = this.node("div",undefined,"room");
          const sample = entry.room_temperatures?.[room.id];
          const value = sample?.[this.displayMode];
          const target = room[this.displayMode+"_target_c"];
          const left = this.node("div",undefined,"label");
          left.append(this.node("strong",room.name));
          const details = this.node("details");
          details.append(this.node("summary",this.t("Senzori","Sensors")+" "+(value?.valid_count??0)+"/"+(value?.configured_count??0)));
          for(const reading of sample?.readings||[]){
            const label = reading.name+": "+(reading.temperature_c==null?"—":reading.temperature_c.toFixed(1)+" °C");
            const age = reading.age_seconds==null?"":this.t(" · raportat acum "," · reported ")+Math.floor(reading.age_seconds/60)+this.t(" min"," min ago");
            details.append(this.node("div",label+age,"muted"));
          }
          left.append(details);
          const right = this.node("div",undefined,"temperature");
          const status = value?.status||"unknown";
          const labels = {within:this.t("În toleranță","Within tolerance"),warm:this.t("Peste țintă","Above target"),cold:this.t("Sub țintă","Below target"),unknown:this.t("Date insuficiente","Insufficient data")};
          const delta = value?.deviation_c;
          right.append(this.node("strong",value?.temperature_c==null?"—":value.temperature_c.toFixed(1)+" °C","status-"+status),
            this.node("small",target==null?this.t("Țintă nesetată","No target"):this.t("Țintă ","Target ")+target.toFixed(1)+" °C"),
            this.node("small",labels[status]+(delta==null?"":" · "+(delta>0?"+":"")+delta.toFixed(1)+" °C"),"status-"+status));
          row.append(left,right);
          section.append(row);
          const hist=entry.history?.[room.id];
          const stats=hist?.windows?.[this.historyHours];
          if(hist){
            const format=v=>v==null?"—":v.toFixed(1)+" °C";
            const prev=hist.yesterday_same_slot_c;
            const readings=sample?.readings||[];
            const fresh=readings.length>0&&readings.every(r=>r.temperature_c!=null&&r.age_seconds!=null&&r.age_seconds<=7200);
            const historyBox=this.node("div",undefined,"history");
            const cells=[[this.t("Ieri, aceeași oră (5 min)","Yesterday, same time (5 min)"),format(prev)],
              [this.t("Diferență față de ieri","Difference from yesterday"),!fresh||prev==null||value?.temperature_c==null?"—":format(value.temperature_c-prev)],
              [this.t("Medie eșantioane","Sample mean"),format(stats?.mean_c)],
              [this.t("Min. / Max.","Min. / Max."),format(stats?.min_c)+" / "+format(stats?.max_c)],
              [this.t("Acoperire","Coverage"),stats?.coverage==null?"—":Math.round(stats.coverage*100)+"% ("+stats.count+"/"+stats.expected+")"]];
            for(const [caption,val] of cells){const cell=this.node("div");cell.append(this.node("small",caption,"muted"),this.node("strong",val));historyBox.append(cell);}
            section.append(historyBox);
          }
        }
        for (const manifold of (t.manifolds||[]).filter(m=>m.floor_id===floor.id)) {
          section.append(this.node("h3",manifold.name));
          const loops = this.node("div",undefined,"loops");
          const circuits = (t.circuits||[]).filter(c=>c.manifold_id===manifold.id).sort((a,b)=>a.position-b.position);
          for (const circuit of circuits) {
            const loop = this.node("div",undefined,"loop");
            const label = this.node("strong",String(circuit.position));
            const meter = this.node("div",undefined,"meter");
            meter.setAttribute("aria-label",this.t("Debit neînregistrat","Flow not recorded"));
            loop.append(label,meter,this.node("div",undefined,"supply"),this.node("div",undefined,"pipe"),this.node("div",undefined,"return"),this.node("div",circuit.name,"label"),this.node("small",rooms.get(circuit.room_id)?.name||this.t("Neasociat","Unassigned"),"muted"),this.node("div","— l/min","muted"));
            loops.append(loop);
          }
          if (!circuits.length) section.append(this.node("p",this.t("Nu există circuite adăugate.","No circuits added."),"muted"));
          section.append(loops);
        }
        main.append(section);
      }
    }
    main.append(this.node("p",this.t("Temperaturile sunt instantanee (media citirilor disponibile), cu toleranță provizorie ±0,3°C. Vechimea citirilor este afișată, dar nu este încă filtrată automat. Istoricul local eșantionează la 5 minute, păstrează 8 zile și exclude rapoartele HA mai vechi de 2 ore; golurile rămân vizibile. Debitele nu sunt încă disponibile. Nu se transmit comenzi instalației.","Temperatures are snapshots (mean of available readings), with provisional ±0.3°C tolerance. Reading age is shown but not yet automatically filtered. Local history samples every 5 minutes, retains 8 days and excludes HA reports older than 2 hours; gaps remain visible. Flows are not yet available. No commands are sent to equipment."),"muted"));
    root.append(main);
  }
}

if (!customElements.get("irpat-efficiency-panel")) customElements.define("irpat-efficiency-panel",IrpatEfficiencyPanel);
