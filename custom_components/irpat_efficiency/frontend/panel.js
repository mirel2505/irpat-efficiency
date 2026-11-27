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
    this.journalDrafts = new Map();
    this.journalSaving = false;
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
    if (!this._hass || this.busy || this.journalSaving || (quiet && this.shadowRoot.querySelector('details.journal[open]'))) return;
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

  journalForm(entry, manifold, circuits) {
    const key = entry.entry_id+":"+manifold.id;
    const draft = this.journalDrafts.get(key)||{flows:{},phase:"observation",previous_id:"",total:"",source:"",note:"",open:false,message:""};
    this.journalDrafts.set(key,draft);
    const box=this.node("details",undefined,"journal");
    box.open=draft.open;
    box.append(this.node("summary",this.t("Înregistrează debitele manual","Record manual flow readings")));
    box.addEventListener("toggle",()=>{if(box.isConnected) draft.open=box.open;});
    const records=(entry.journal||[]).filter(r=>r.manifold_id===manifold.id).reverse();
    const previous=this.node("select");
    previous.append(new Option(this.t("Alege înregistrarea inițială","Choose initial observation"),""));
    for(const record of records.filter(r=>r.phase==="before")){
      previous.append(new Option(new Date(record.timestamp).toLocaleString(),record.id));
    }
    previous.value=draft.previous_id;
    previous.addEventListener("change",()=>{draft.previous_id=previous.value;});
    const phase=this.node("select");
    for(const [value,ro,en] of [["observation","Observație","Observation"],["before","Înainte de reglaj","Before adjustment"],["after","După reglaj","After adjustment"]]) phase.append(new Option(this.t(ro,en),value));
    phase.value=draft.phase;
    const previousLabel=this.node("label",this.t("Înregistrare inițială","Initial observation"));
    previousLabel.append(previous);
    previousLabel.hidden=draft.phase!=="after";
    phase.addEventListener("change",()=>{draft.phase=phase.value;previousLabel.hidden=draft.phase!=="after";if(draft.phase!=="after")draft.previous_id="";});
    const phaseLabel=this.node("label",this.t("Tip înregistrare","Observation type"));
    phaseLabel.append(phase);
    const form=this.node("form");
    form.append(phaseLabel,previousLabel);
    const fields=this.node("div",undefined,"flow-fields");
    const numeric=(caption,value,update)=>{
      const label=this.node("label",caption);
      const input=this.node("input");input.type="number";input.min="0";input.step="any";input.value=value??"";
      input.placeholder="—";
      input.addEventListener("input",()=>update(input.value));
      label.append(input);return label;
    };
    for(const circuit of circuits) fields.append(numeric(circuit.position+". "+circuit.name+" (l/min)",draft.flows[circuit.id],v=>{draft.flows[circuit.id]=v;}));
    form.append(fields,numeric(this.t("Debit total distribuitor (l/min)","Manifold total (l/min)"),draft.total,v=>{draft.total=v;}),
      numeric(this.t("Debit sursă termică (m³/h)","Heat source flow (m³/h)"),draft.source,v=>{draft.source=v;}));
    const noteLabel=this.node("label",this.t("Observații","Notes"));
    const note=this.node("textarea");note.maxLength=2000;note.value=draft.note;
    note.addEventListener("input",()=>{draft.note=note.value;});noteLabel.append(note);form.append(noteLabel);
    form.append(this.node("p",this.t("Lasă necompletate măsurătorile necunoscute. Introdu doar valori citite fizic. Nu se comandă debitmetrele.","Leave unknown readings blank. Enter physical observations only. Flow meters are not controlled."),"muted"));
    const save=this.node("button",this.t("Salvează observația","Save observation"));save.type="submit";save.disabled=this.journalSaving||!circuits.length;
    const message=this.node("p",draft.message,"muted");message.setAttribute("role","status");
    form.append(save,message);
    form.addEventListener("submit",async event=>{
      event.preventDefault();
      if(this.journalSaving||!this._hass) return;
      const readings=Object.fromEntries(circuits.filter(c=>draft.flows[c.id]!==undefined&&draft.flows[c.id]!=="").map(c=>[c.id,Number(draft.flows[c.id])]));
      if(!Object.keys(readings).length|| (draft.phase==="after"&&!draft.previous_id)){
        message.textContent=this.t("Introdu cel puțin un debit și alege referința pentru reglajul ulterior.","Enter at least one reading and select a reference for an after observation.");return;
      }
      const request={type:"irpat_efficiency/journal_append",entry_id:entry.entry_id,manifold_id:manifold.id,readings,phase:draft.phase,note:draft.note};
      if(draft.phase==="after")request.previous_id=draft.previous_id;
      if(draft.total!=="")request.manifold_total_lmin=Number(draft.total);
      if(draft.source!=="")request.source_total_m3h=Number(draft.source);
      this.journalSaving=true;save.disabled=true;
      try{
        await this._hass.callWS(request);
        this.journalDrafts.delete(key);
      }catch(error){
        draft.message=this.t("Salvarea nu a fost confirmată. Verifică jurnalul înainte de a reîncerca.","Save not confirmed. Check journal before retrying.");
        message.textContent=draft.message;
        return;
      }finally{this.journalSaving=false;save.disabled=false;}
      await this.refresh();
    });
    box.append(form);
    const recent=this.node("div",undefined,"journal-recent");
    recent.append(this.node("h4",this.t("Ultimele observații","Recent observations")));
    for(const record of records.slice(0,5)){
      const row=this.node("div",undefined,"journal-record");
      const phaseLabel={before:this.t("Înainte","Before"),after:this.t("După","After"),observation:this.t("Observație","Observation")};
      row.append(this.node("strong",new Date(record.timestamp).toLocaleString()+" · "+(phaseLabel[record.phase]||record.phase)));
      const labels=new Map(circuits.map(c=>[c.id,c.name]));
      for(const [id,value] of Object.entries(record.flows_lmin||{}))row.append(this.node("small",(labels.get(id)||this.t("Circuit arhivat","Archived circuit"))+": "+(value==null?"—":value.toFixed(2)+" l/min")));
      row.append(this.node("small",this.t("Total distribuitor: ","Manifold total: ")+(record.manifold_total_lmin==null?"—":record.manifold_total_lmin.toFixed(2)+" l/min")));
      row.append(this.node("small",this.t("Debit sursă: ","Source flow: ")+(record.source_total_m3h==null?"—":record.source_total_m3h.toFixed(2)+" m³/h")));
      if(record.note)row.append(this.node("p",record.note));
      recent.append(row);
    }
    if(!records.length)recent.append(this.node("p",this.t("Nicio observație salvată.","No saved observations."),"muted"));
    box.append(recent);
    return box;
  }

  thermalDiagnostics(entry) {
    const box=this.node("section",undefined,"card");
    box.append(this.node("h2",this.t("Analiză termică pe zone · 24 h","Thermal diagnostics by zone · 24 h")));
    const zones=Object.values(entry.thermal_diagnostics?.[this.displayMode]||{});
    const labels={
      configuration_collecting:this.t("Colectare după configurare sau salvare nereușită","Collecting after configuration or save failure"),
      shared_rooms:this.t("Încăperi deservite de mai multe zone; analiză separată suspendată","Rooms served by multiple zones; separate analysis suspended"),
      monitor_only:this.t("Doar monitorizare","Monitoring only"),
      settling:this.t("În stabilizare după observația de reglaj","Settling after adjustment observation"),
      insufficient_data:this.t("Date insuficiente","Insufficient data"),
      observed:this.t("Observație statistică","Statistical observation")
    };
    const patterns={
      mixed:this.t("Abatere comună și diferențe locale","Common error and local differences"),
      distribution:this.t("Diferențe între încăperi","Differences between rooms"),
      common:this.t("Abatere generală","Common error"),
      near_targets:this.t("Medii apropiate de ținte","Means near targets")
    };
    const format=v=>v==null?"—":(v>0?"+":"")+v.toFixed(2)+" °C";
    const names=new Map((entry.topology.rooms||[]).map(r=>[r.id,r.name]));
    for(const zone of zones){
      box.append(this.node("h3",zone.name),this.node("p",labels[zone.status]||zone.status));
      const stable=zone.stability;
      if(stable){
        const progress=this.node("progress");
        progress.max=stable.required_days;progress.value=stable.consecutive_days;
        progress.setAttribute("aria-label",this.t("Zile consecutive în criterii","Consecutive days meeting criteria"));
        const stateLabels={
          stable_observed:this.t("Stabilitate termică observată","Observed thermal stability"),
          criteria_not_met:this.t("Criteriile zilnice nu sunt îndeplinite","Daily criteria not met"),
          collecting:this.t("Colectare pentru confirmare","Collecting for confirmation"),
          settling:this.t("Stabilizare","Settling"),
          monitor_only:this.t("Doar monitorizare","Monitoring only")
        };
        box.append(this.node("p",(stateLabels[stable.status]||stable.status)+" · "+stable.consecutive_days+"/"+stable.required_days+" "+this.t("zile","days")),progress);
        box.append(this.node("small",this.t("Intervale consecutive de 24 h: acoperire comună ≥90%, minimum 95% dintre eșantioanele comune în toleranța ±0,3°C pentru fiecare cameră. Nu confirmă regimul real sau echilibrarea hidraulică.","Consecutive 24 h windows: ≥90% common coverage, at least 95% of common samples within ±0.3°C for each room. Does not confirm actual operating mode or hydraulic balance."),"muted"));
      }
      if(zone.status==="observed"||zone.status==="insufficient_data")
        box.append(this.node("small",this.t("Acoperire comună: ","Common coverage: ")+Math.round(zone.coverage*100)+"%","muted"));
      if(zone.status==="observed"){
        box.append(this.node("p",patterns[zone.pattern]||zone.pattern),
          this.node("p",this.t("Abatere generală: ","Common error: ")+format(zone.common_error_c)));
        box.append(this.node("small",zone.weighting==="area"?this.t("Ponderare după suprafață","Area weighting"):this.t("Ponderare egală pe încăperi","Equal room weighting"),"muted"));
        for(const [id,r] of Object.entries(zone.rooms)){
          const row=this.node("div",undefined,"room");
          row.append(this.node("span",names.get(id)||id),
            this.node("span",this.t("Abatere ","Error ")+format(r.mean_error_c)+" · "+this.t("Rezidual ","Residual ")+format(r.residual_c)+" · "+Math.round(r.within_fraction*100)+"% "+this.t("în toleranță","within tolerance")));
          box.append(row);
        }
      }
    }
    if(!zones.length)box.append(this.node("p",this.t("Nicio zonă disponibilă.","No available zones.")));
    box.append(this.node("p",this.t("Rezultate descriptive pentru ținta selectată; regimul real, vremea și perturbările nu sunt încă validate. Nu reprezintă recomandări de reglaj sau confirmarea echilibrării.","Descriptive results for the selected target; actual operating mode, weather and disturbances are not yet validated. These are not adjustment recommendations or balance confirmation."),"muted"));
    return box;
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
      .journal{margin:12px 0}.journal form{display:grid;gap:10px;padding:10px 0}.journal label{display:grid;gap:4px;overflow-wrap:anywhere}.journal input,.journal select,.journal textarea{width:100%;box-sizing:border-box;min-width:0;padding:8px;border:1px solid var(--divider-color);border-radius:6px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}.journal label[hidden]{display:none}.flow-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:8px}.journal-record{border-top:1px solid var(--divider-color);padding:8px 0}.journal-record small{display:block}.journal-record p{white-space:pre-wrap;overflow-wrap:anywhere}
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
      main.append(grid,this.thermalDiagnostics(entry));
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
          section.append(loops,this.journalForm(entry,manifold,circuits));
        }
        main.append(section);
      }
    }
    main.append(this.node("p",this.t("Temperaturile sunt instantanee (media citirilor disponibile), cu toleranță provizorie ±0,3°C. Vechimea citirilor este afișată, dar nu este încă filtrată automat. Istoricul local eșantionează la 5 minute, păstrează 8 zile și exclude rapoartele HA mai vechi de 2 ore; golurile rămân vizibile. Debitele se înregistrează manual în jurnal; nu sunt citiri live. Nu se transmit comenzi instalației.","Temperatures are snapshots (mean of available readings), with provisional ±0.3°C tolerance. Reading age is shown but not yet automatically filtered. Local history samples every 5 minutes, retains 8 days and excludes HA reports older than 2 hours; gaps remain visible. Flows are recorded manually in the journal; they are not live readings. No commands are sent to equipment."),"muted"));
    root.append(main);
  }
}

if (!customElements.get("irpat-efficiency-panel")) customElements.define("irpat-efficiency-panel",IrpatEfficiencyPanel);
