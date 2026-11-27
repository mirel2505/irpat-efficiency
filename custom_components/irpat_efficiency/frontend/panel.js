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
    this.viewMode = 'simple';
    this.historyHours = '24';
    this.timer = null;
    this.journalDrafts = new Map();
    this.exportUrls = new Set();
    this.journalSaving = false;
    this.setup = null;
    this.setupBusy = false;
    this.setupStep = 0;
    this.setupMessage = '';
    this.setupError = '';
    this.reviewedWindows = new Set();
    this.balanceMessage = '';
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
    this.clearExportUrls();
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }

  async refresh(quiet = false) {
    if (!this._hass || this.busy || this.journalSaving || this.setup || this.setupBusy || (quiet && (this.shadowRoot.querySelector('details.journal[open], details.room-detail[open]') || this.shadowRoot.activeElement?.closest?.('.balance-form')))) return;
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

  recordedFlow(entry, manifold, circuit) {
    // Use the latest observation of this manifold, not a mixture of readings
    // from different dates. Missing is unknown; zero is a measured value.
    const records=(entry.journal||[]).filter(r=>r.manifold_id===manifold.id &&
      Number.isFinite(Date.parse(r.timestamp)));
    const latest=records.reduce((a,b)=>!a||Date.parse(b.timestamp)>=Date.parse(a.timestamp)?b:a,null);
    const value=latest?.flows_lmin?.[circuit.id];
    return {value:Number.isFinite(value)&&value>=0?value:null,timestamp:latest?.timestamp||null};
  }

  card(title, value) {
    const e = this.node("div", undefined, "card metric");
    e.append(this.node("div", title, "muted"), this.node("strong", value));
    return e;
  }

  flowSummary(circuits, flows) {
    const values=circuits.map(c=>flows[c.id]).filter(v=>v!==undefined&&v!==null&&String(v).trim()!==""&&Number.isFinite(Number(v))&&Number(v)>=0).map(Number);
    return {count:values.length,total:values.reduce((a,b)=>a+b,0),complete:circuits.length>0&&values.length===circuits.length};
  }

  journalFlowValue(state) {
    const factors={"m³/h":1,"m3/h":1,"L/min":0.06,"l/min":0.06,"L/h":0.001,"l/h":0.001};
    const unit=state?.attributes?.unit_of_measurement,raw=state?.state;
    if(!Object.prototype.hasOwnProperty.call(factors,unit)||raw==null||String(raw).trim()==="")return null;
    const value=Number(raw)*factors[unit];
    return Number.isFinite(value)&&value>=0?value:null;
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
    const review=entry.balance_advice?.[manifold.zone_id];
    if(review?.last_adjustment_at!=null){
      const status=this.node("div",undefined,"journal-record");
      status.append(this.node("strong",this.t("Monitorizare după reglaj · zonă","Post-adjustment monitoring · zone")),
        this.node("small",this.t("Ultima referință/reglaj: ","Last baseline/adjustment: ")+new Date(review.last_adjustment_at*1000).toLocaleString()),
        this.node("small",this.t("Timp trecut: ","Elapsed: ")+review.elapsed_hours.toFixed(1)+" h"),
        this.node("small",review.remaining_hours>0?this.t("Reevaluare cel mai devreme: ","Earliest reassessment: ")+new Date(review.earliest_review_at*1000).toLocaleString():this.t("Intervalul minim a trecut; verifică disponibilitatea recomandărilor.","Minimum interval elapsed; check advice availability.")));
      box.append(status);
    }
    const previous=this.node("select");
    previous.append(new Option(this.t("Alege înregistrarea inițială","Choose initial observation"),""));
    const updatePrevious=()=>{
      previous.replaceChildren(new Option(this.t("Alege înregistrarea inițială","Choose initial observation"),""));
      for(const record of records.filter(r=>draft.phase==="adjustment"||r.phase==="before"))previous.append(new Option(new Date(record.timestamp).toLocaleString(),record.id));
      previous.value=draft.previous_id|| (draft.phase==="adjustment"?records[0]?.id||"":"");
      draft.previous_id=previous.value;
    };
    updatePrevious();
    previous.addEventListener("change",()=>{draft.previous_id=previous.value;});
    const phase=this.node("select");
    for(const [value,ro,en] of [["observation","Observație","Observation"],["before","Înainte de reglaj","Before adjustment"],["after","După reglaj","After adjustment"],["adjustment","Am modificat debitmetre","I adjusted flow meters"]]) phase.append(new Option(this.t(ro,en),value));
    phase.value=draft.phase;
    const previousLabel=this.node("label",this.t("Înregistrare inițială","Initial observation"));
    previousLabel.append(previous);
    const adjusting=()=>["after","adjustment"].includes(draft.phase);
    previousLabel.hidden=!adjusting();
    draft.adjusted=draft.adjusted||{};
    const adjustmentHint=this.node("p",this.t("Bifează numai debitmetrele pe care le-ai reglat fizic. Recitește toate circuitele, inclusiv cele neatinse; nu copia automat citirile vechi.","Tick only physically adjusted meters. Remeasure all loops, including untouched ones; do not copy old readings."),"muted");
    adjustmentHint.hidden=!adjusting();
    const adjustmentChecks=[];
    phase.addEventListener("change",()=>{draft.phase=phase.value;previousLabel.hidden=!adjusting();adjustmentHint.hidden=!adjusting();for(const l of adjustmentChecks)l.hidden=!adjusting();draft.previous_id="";updatePrevious();});
    const phaseLabel=this.node("label",this.t("Tip înregistrare","Observation type"));
    phaseLabel.append(phase);
    const form=this.node("form");
    form.append(phaseLabel,previousLabel,adjustmentHint);
    const fields=this.node("div",undefined,"flow-fields");
    const numeric=(caption,value,update)=>{
      const label=this.node("label",caption);
      const input=this.node("input");input.type="number";input.min="0";input.step="any";input.value=value??"";
      input.placeholder="—";
      input.addEventListener("input",()=>update(input.value));
      label.append(input);return label;
    };
    const totalLabel=this.node("label",this.t("Debit total distribuitor (l/min)","Manifold total (l/min)"));
    const total=this.node("input");total.type="text";total.readOnly=true;total.placeholder="—";
    const coverage=this.node("small",undefined,"muted");
    totalLabel.append(total,coverage);
    const updateTotal=()=>{
      const sum=this.flowSummary(circuits,draft.flows);
      total.value=sum.count?sum.total.toFixed(2):"";
      coverage.textContent=sum.count+"/"+circuits.length+" · "+(sum.complete?this.t("Total calculat automat","Automatically calculated total"):this.t("Sumă parțială — nu este totalul distribuitorului","Partial sum — not manifold total"));
    };
    for(const circuit of circuits){
      const room=entry.topology?.rooms?.find(r=>r.id===circuit.room_id);
      const caption=circuit.position+". "+(room?.name||circuit.name)+" (l/min)";
      const item=this.node("div");
      const flag=this.node("label",this.t("Reglat fizic","Physically adjusted"));
      const check=this.node("input");check.type="checkbox";check.checked=!!draft.adjusted[circuit.id];flag.prepend(check);
      check.addEventListener("change",()=>{draft.adjusted[circuit.id]=check.checked;});
      flag.hidden=!adjusting();adjustmentChecks.push(flag);
      item.append(numeric(caption,draft.flows[circuit.id],v=>{draft.flows[circuit.id]=v;updateTotal();}),flag);fields.append(item);
    }
    updateTotal();form.append(fields,totalLabel);
    const methodLabel=this.node("label",this.t("Debit sursă termică — metodă","Heat source flow — method"));
    const method=this.node("select");
    method.append(new Option(this.t("Introducere manuală","Manual entry"),"manual"),new Option(this.t("Senzor Home Assistant","Home Assistant sensor"),"sensor"));
    method.value=draft.sourceMethod||"manual";methodLabel.append(method);form.append(methodLabel);
    const manual=numeric(this.t("Debit sursă termică (m³/h)","Heat source flow (m³/h)"),draft.source,v=>{draft.source=v;});
    const sensorLabel=this.node("label",this.t("Entitate debit sursă","Source flow entity"));
    const select=this.node("select");select.append(new Option(this.t("Alege entitatea…","Choose entity…"),""));
    const linkedIds=new Set((entry.topology?.telemetry||[]).filter(b=>b.group==="sources"&&b.role==="flow"&&entry.topology.sources.some(s=>s.id===b.owner_id&&s.zone_ids?.includes(manifold.zone_id))).map(b=>b.entity_id));
    const units=["m³/h","m3/h","L/min","l/min","L/h","l/h"];
    const candidates=Object.entries(this._hass?.states||{}).filter(([id,s])=>id.startsWith("sensor.")&&(linkedIds.has(id)||units.includes(s.attributes?.unit_of_measurement)));
    for(const [id,s] of candidates.sort((a,b)=>Number(linkedIds.has(b[0]))-Number(linkedIds.has(a[0]))||a[0].localeCompare(b[0])))
      select.append(new Option((linkedIds.has(id)?"★ ":"")+(s.attributes?.friendly_name||id)+" ("+id+")",id));
    if(draft.sourceEntity&&!candidates.some(([id])=>id===draft.sourceEntity))select.append(new Option(draft.sourceEntity,draft.sourceEntity));
    select.value=draft.sourceEntity||(linkedIds.size===1&&candidates.some(([id])=>linkedIds.has(id))?[...linkedIds][0]:"");
    const preview=this.node("small",undefined,"muted");
    sensorLabel.append(select,preview);
    const updateSource=()=>{
      draft.sourceMethod=method.value;draft.sourceEntity=select.value;
      manual.hidden=method.value!=="manual";sensorLabel.hidden=method.value!=="sensor";
      const value=this.journalFlowValue(this._hass?.states?.[select.value]);
      preview.textContent=(value==null?this.t("Citire indisponibilă","Reading unavailable"):value.toFixed(3)+" m³/h")+" · "+this.t("Citirea este verificată și preluată la salvare.","Reading is validated and captured on save.");
    };
    method.addEventListener("change",updateSource);select.addEventListener("change",updateSource);
    updateSource();form.append(manual,sensorLabel);
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
      if(!Object.keys(readings).length|| (adjusting()&&!draft.previous_id)){
        message.textContent=this.t("Introdu cel puțin un debit și alege referința pentru reglajul ulterior.","Enter at least one reading and select a reference for an after observation.");return;
      }
      const request={type:"irpat_efficiency/journal_append",entry_id:entry.entry_id,manifold_id:manifold.id,readings,phase:draft.phase,note:draft.note};
      if(adjusting()){
        request.previous_id=draft.previous_id;
        request.adjusted_circuit_ids=circuits.filter(c=>draft.adjusted[c.id]).map(c=>c.id);
        if(draft.phase==="adjustment"&&!request.adjusted_circuit_ids.length){message.textContent=this.t("Bifează debitmetrul reglat fizic.","Tick the physically adjusted meter.");return;}
        if(request.adjusted_circuit_ids.some(id=>!(id in readings))){message.textContent=this.t("Introdu debitul nou al fiecărui circuit reglat.","Enter the new reading for each adjusted loop.");return;}
      }
      // The server calculates the manifold total only from complete readings.
      if(draft.sourceMethod==="sensor"){
        if(!draft.sourceEntity){message.textContent=this.t("Alege senzorul de debit.","Choose a flow sensor.");return;}
        request.source_flow_entity_id=draft.sourceEntity;
      }else if(draft.source!=="")request.source_total_m3h=Number(draft.source);
      this.journalSaving=true;save.disabled=true;
      try{
        await this._hass.callWS(request);
        this.journalDrafts.delete(key);
      }catch(error){
        draft.message=error?.code==="invalid_observation"&&String(error.message).includes("source_flow")?
          this.t("Senzorul de debit este indisponibil, prea vechi sau incompatibil. Verifică-l ori alege introducerea manuală.","Flow sensor is unavailable, stale or incompatible. Review it or choose manual entry."):
          this.t("Salvarea nu a fost confirmată. Verifică jurnalul înainte de a reîncerca.","Save not confirmed. Check journal before retrying.");
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
      const phaseLabel={before:this.t("Înainte","Before"),after:this.t("După","After"),observation:this.t("Observație","Observation"),adjustment:this.t("Reglaj efectuat","Adjustment made")};
      row.append(this.node("strong",new Date(record.timestamp).toLocaleString()+" · "+(phaseLabel[record.phase]||record.phase)));
      const labels=new Map(circuits.map(c=>[c.id,c.name]));
      for(const [id,value] of Object.entries(record.flows_lmin||{}))row.append(this.node("small",(labels.get(id)||this.t("Circuit arhivat","Archived circuit"))+": "+(value==null?"—":value.toFixed(2)+" l/min")));
      for(const [id,c] of Object.entries(record.flow_changes||{})){
        const diff=c.difference_lmin;
        const kind=c.direct_adjustment===true?this.t("Reglat fizic","Physically adjusted"):c.direct_adjustment===false?this.t("Nereglat direct","Not directly adjusted"):this.t("Reglaj necunoscut","Adjustment unknown");
        row.append(this.node("small",(labels.get(id)||id)+" · "+kind+" · "+c.before_lmin.toFixed(2)+" → "+c.after_lmin.toFixed(2)+" l/min ("+(diff>=0?"+":"")+diff.toFixed(2)+")"));
      }
      row.append(this.node("small",this.t("Total distribuitor: ","Manifold total: ")+(record.manifold_total_lmin==null?"—":record.manifold_total_lmin.toFixed(2)+" l/min")));
      row.append(this.node("small",this.t("Debit sursă: ","Source flow: ")+(record.source_total_m3h==null?"—":record.source_total_m3h.toFixed(2)+" m³/h")));
      const sourceInfo=record.context?.source_flow;
      if(sourceInfo?.method==="sensor")row.append(this.node("small",this.t("Senzor: ","Sensor: ")+sourceInfo.entity_id,"muted"));
      else if(sourceInfo?.method==="manual")row.append(this.node("small",this.t("Debit sursă introdus manual","Source flow entered manually"),"muted"));
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
      duplicate_temperature_sensor:this.t("Senzor de temperatură reutilizat; analiza independentă este suspendată","Reused temperature sensor; independent analysis suspended"),
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

  referenceProfiles(entry) {
    const box=this.node("section",undefined,"card");
    box.append(this.node("h2",this.t("Profiluri hidraulice de referință","Hydraulic reference profiles")));
    const t=entry.topology;
    const names=new Map((t.circuits||[]).map(c=>[c.id,c.name]));
    const profiles=entry.profiles||[];
    for(const p of profiles){
      const detail=this.node("details",undefined,"journal");
      detail.append(this.node("summary",p.name+" · "+p.mode+" · "+new Date(p.created_at).toLocaleString()));
      for(const [id,v] of Object.entries(p.flows_lmin||{}))
        detail.append(this.node("div",(names.get(id)||id)+": "+v.toFixed(2)+" l/min"));
      detail.append(this.node("small",this.t("Valori istorice; nu reprezintă debite țintă obligatorii. Restaurarea se face doar manual.","Historical values, not mandatory flow targets. Restoration is manual only."),"muted"));
      const observations=(entry.journal||[]).filter(s=>p.references?.[s.manifold_id] && (t.manifolds||[]).some(m=>m.id===s.manifold_id));
      if(observations.length){
        const label=this.node("label",this.t("Compară cu observația","Compare with observation"));
        const select=this.node("select");
        for(const s of observations.slice().reverse()){
          const manifold=(t.manifolds||[]).find(m=>m.id===s.manifold_id);
          select.append(new Option(manifold.name+" · "+new Date(s.timestamp).toLocaleString(),s.id));
        }
        label.append(select);
        const button=this.node("button",this.t("Compară debitele","Compare flows"));button.type="button";
        const output=this.node("div");output.setAttribute("role","status");
        select.addEventListener("change",()=>output.replaceChildren());
        button.addEventListener("click",async()=>{
          if(!this._hass||this.busy||this.journalSaving)return;
          this.journalSaving=true;button.disabled=true;select.disabled=true;output.replaceChildren();
          try{
            const result=await this._hass.callWS({type:"irpat_efficiency/profile_review",entry_id:entry.entry_id,profile_id:p.id,snapshot_id:select.value});
            if(!detail.isConnected)return;
            const fmt=v=>Number.isFinite(v)?v.toFixed(2)+" l/min":"—";
            for(const row of result.rows){
              output.append(this.node("p",row.position+". "+row.name+" · "+this.t("Referință: ","Reference: ")+fmt(row.reference_lmin)+" · "+this.t("Observat: ","Observed: ")+fmt(row.observed_lmin)+" · Δ "+fmt(row.difference_lmin)));
            }
            output.append(this.node("small",this.t("Diferențe brute, fără confirmarea condițiilor comparabile. Nu sunt instrucțiuni de reglaj.","Raw differences without confirmation of comparable conditions. Not adjustment instructions."),"muted"));
          }catch(error){
            if(detail.isConnected)output.textContent=this.t("Comparație indisponibilă: verifică dacă circuitele și zona corespund profilului.","Comparison unavailable: check that circuits and zone match the profile.");
          }finally{this.journalSaving=false;button.disabled=false;select.disabled=false;}
        });
        detail.append(label,button,output);
      }
      box.append(detail);
    }
    const create=this.node("details",undefined,"journal");
    create.append(this.node("summary",this.t("Salvează profil din jurnal","Save a profile from journal")));
    const form=this.node("form");
    const name=this.node("input");name.required=true;name.maxLength=120;name.placeholder=this.t("Denumirea profilului","Profile name");
    const nameLabel=this.node("label",this.t("Denumire","Name"));nameLabel.append(name);
    const zone=this.node("select");zone.required=true;
    for(const z of t.zones||[])zone.append(new Option(z.name,z.id));
    const zoneLabel=this.node("label",this.t("Zonă","Zone"));zoneLabel.append(zone);
    const selectors=this.node("div");const fields=[];
    const rebuild=()=>{
      selectors.replaceChildren();fields.length=0;
      for(const m of (t.manifolds||[]).filter(x=>x.zone_id===zone.value)){
        const label=this.node("label",m.name);
        const select=this.node("select");select.required=true;
        select.append(new Option(this.t("Alege observația","Choose observation"),""));
        const ids=(t.circuits||[]).filter(c=>c.manifold_id===m.id).map(c=>c.id);
        for(const s of (entry.journal||[]).filter(s=>s.manifold_id===m.id).slice().reverse()){
          const flows=s.flows_lmin||{};
          if(ids.length&&Object.keys(flows).length===ids.length&&ids.every(id=>Number.isFinite(flows[id])&&flows[id]>=0))
            select.append(new Option(new Date(s.timestamp).toLocaleString(),s.id));
        }
        label.append(select);selectors.append(label);fields.push(select);
      }
    };
    zone.addEventListener("change",rebuild);rebuild();
    const mode=this.node("select");mode.append(new Option(this.t("Încălzire","Heating"),"heating"),new Option(this.t("Răcire","Cooling"),"cooling"));mode.value=this.displayMode;
    const modeLabel=this.node("label",this.t("Regim de referință","Reference mode"));modeLabel.append(mode);
    const submit=this.node("button",this.t("Salvează profilul","Save profile"));submit.type="submit";
    const msg=this.node("p","");msg.setAttribute("role","status");
    form.append(nameLabel,zoneLabel,modeLabel,selectors,submit,msg);
    form.addEventListener("submit",async ev=>{
      ev.preventDefault();
      if(this.journalSaving||!this._hass)return;
      if(!fields.length||fields.some(f=>!f.value)){msg.textContent=this.t("Sunt necesare observații complete pentru toate distribuitoarele.","Complete observations are required for all manifolds.");return;}
      this.journalSaving=true;submit.disabled=true;
      try{
        await this._hass.callWS({type:"irpat_efficiency/profile_create",entry_id:entry.entry_id,zone_id:zone.value,name:name.value,mode:mode.value,snapshot_ids:fields.map(f=>f.value)});
      }catch(error){msg.textContent=this.t("Salvarea nu a fost confirmată. Verifică lista înainte de reîncercare.","Save not confirmed. Check list before retrying.");return;}
      finally{this.journalSaving=false;submit.disabled=false;}
      await this.refresh();
    });
    create.append(form);box.append(create);
    box.append(this.node("small",this.t("Profilul păstrează măsurători manuale, nu certifică echilibrarea. Observațiile pot fi din momente diferite.","A profile preserves manual readings, not balance certification. Observations may be from different times."),"muted"));
    return box;
  }

  // Reviews use saved data on the server and never write equipment settings.
  reviewButton(entry, form, request, output, show) {
    const button=this.node("button",this.t("Analizează","Analyze"));button.type="submit";
    form.append(button,output);output.setAttribute("role","status");
    form.addEventListener("submit",async ev=>{
      ev.preventDefault();
      if(!this._hass||this.busy||this.journalSaving)return;
      this.journalSaving=true;button.disabled=true;output.replaceChildren();
      try{
        const result=await this._hass.callWS({entry_id:entry.entry_id,...request()});
        if(output.isConnected)show(result);
      }catch(error){
        if(output.isConnected)output.textContent=this.t("Analiză indisponibilă. Verifică perioada, configurația și istoricul intervențiilor.","Analysis unavailable. Check the interval, configuration and adjustment history.")+" ("+String(error?.message||"")+")";
      }finally{this.journalSaving=false;button.disabled=false;}
    });
  }

  reviewCheckbox(form,label) {
    const l=this.node("label"),i=this.node("input");i.type="checkbox";i.required=true;
    l.append(i,document.createTextNode(" "+label));form.append(l);return i;
  }

  weatherObservations(entry) {
    const box=this.node("section",undefined,"card");
    box.append(this.node("h2",this.t("Observații climatice","Weather observations")));
    if(!entry.topology.outdoor_entity_id){
      box.append(this.node("p",this.t("Selectează un senzor exterior în configurare.","Select an outdoor sensor in configuration.")));
      return box;
    }
    const observations=entry.weather_observations||{};
    for(const z of entry.topology.zones||[]){
      box.append(this.node("h3",z.name));
      const rows=observations[z.id]||[];
      if(!rows.length){
        box.append(this.node("p",this.t("Se colectează date sau zona nu poate fi analizată separat.","Collecting data or zone cannot be analyzed separately."),"muted"));continue;
      }
      const detail=this.node("details",undefined,"journal");
      detail.append(this.node("summary",this.t("Selectează perioadele comparabile","Select comparable periods")));
      const form=this.node("form"),choices=[];
      for(const d of rows){
        const label=this.node("label"),check=this.node("input");check.type="checkbox";
        check.disabled=d.coverage<0.9||d.common_error_c==null||d.outdoor_c==null||d.max_residual_c>0.300000001||d.relative_balance_fraction<0.95;
        const temp=v=>v==null?"—":v.toFixed(2)+" °C";
        label.append(check,document.createTextNode(" "+new Date(d.start*1000).toLocaleString()+" — "+new Date(d.end*1000).toLocaleString()+" · "+this.t("Exterior ","Outdoor ")+temp(d.outdoor_c)+" · "+this.t("Abatere ","Error ")+temp(d.common_error_c)+" · "+Math.round(d.coverage*100)+"%"));
        choices.push({check,start:d.start});form.append(label);
      }
      const reviewed=this.reviewCheckbox(form,this.t("Confirm încălzirea continuă, condiții comparabile, aceeași curbă și lipsa intervențiilor neînregistrate în perioadele selectate.","I confirm continuous heating, comparable conditions, unchanged curve and no unrecorded interventions in the selected periods."));
      const output=this.node("div");
      this.reviewButton(entry,form,()=>({type:"irpat_efficiency/curve_review",zone_id:z.id,end:rows[0].end,
        starts:choices.filter(x=>x.check.checked).map(x=>x.start),reviewed:reviewed.checked}),output,r=>{
        const labels={balance_required:this.t("Meteoreglare blocată: echilibrează mai întâi încăperile","Weather curve blocked: balance rooms first"),balance_data_required:this.t("Date insuficiente pentru echilibrul întregii surse","Insufficient source-wide balance data"),settling:this.t("Așteaptă stabilizarea după reglaj","Wait for settling after adjustment"),weather_not_comparable:this.t("Condiții meteo necomparabile","Weather conditions not comparable"),no_common_error:this.t("Abatere generală neconfirmată","Common error not confirmed"),review_slope:this.t("Verifică panta curbei","Review curve slope"),review_offset:this.t("Verifică deplasarea curbei","Review curve offset"),review_fixed_supply:this.t("Verifică temperatura de tur","Review supply temperature"),near_targets:this.t("Aproape de ținte","Near targets"),insufficient_data:this.t("Date insuficiente","Insufficient data"),monitor_only:this.t("Doar monitorizare","Monitoring only"),weather_changed:this.t("Condiții exterioare diferite","Outdoor conditions changed"),inconclusive:this.t("Rezultat neconcludent","Inconclusive"),duplicate_day:this.t("Perioadă duplicată","Duplicate period")};
        const directions={raise:this.t("Sens de analizat: creștere","Direction to review: increase"),lower:this.t("Sens de analizat: reducere","Direction to review: decrease"),steeper:this.t("Sens de analizat: pantă mai mare","Direction to review: steeper slope"),flatter:this.t("Sens de analizat: pantă mai mică","Direction to review: flatter slope")};
        output.append(this.node("p",labels[r.status]||r.status),this.node("small",this.t("Perioade utilizate: ","Periods used: ")+r.days));
        if(r.direction)output.append(this.node("p",directions[r.direction]||r.direction));
        output.append(this.node("small",this.t("Ipoteză bazată pe observații confirmate manual; nu este o setare calculată sau o comandă.","Hypothesis from manually reviewed observations; not a calculated setting or command."),"muted"));
      });
      detail.append(form);box.append(detail);
    }
    box.append(this.node("small",this.t("Ferestre de 24 h. Sunt necesare minimum 3 perioade eligibile, respectiv 5 pentru pantă și o variație exterioară de minimum 5°C. Regimul real nu este certificat automat.","24-hour windows. At least 3 eligible periods, or 5 with at least 5°C outdoor span for slope review. Actual operation is not automatically certified."),"muted"));
    return box;
  }

  inertiaReview(entry) {
    const detail=this.node("details",undefined,"card journal");
    detail.append(this.node("summary",this.t("Inerție termică – răcire naturală","Thermal inertia – natural cooling")));
    if(!entry.topology.outdoor_entity_id||!(entry.topology.rooms||[]).length){
      detail.append(this.node("p",this.t("Sunt necesare o cameră și temperatura exterioară.","A room and outdoor temperature are required.")));return detail;
    }
    const form=this.node("form"),room=this.node("select");room.required=true;
    for(const r of entry.topology.rooms)room.append(new Option(r.name,r.id));
    const label=this.node("label",this.t("Cameră","Room"));label.append(room);form.append(label);
    const time=(title)=>{
      const l=this.node("label",title),i=this.node("input");i.type="datetime-local";i.step="300";i.required=true;l.append(i);form.append(l);return i;
    };
    const start=time(this.t("Început (ora locală a browserului)","Start (browser local time)"));
    const end=time(this.t("Sfârșit (ora locală a browserului)","End (browser local time)"));
    const off=this.reviewCheckbox(form,this.t("Confirm că nu a existat aport activ de încălzire sau răcire în acest interval.","I confirm there was no active heating or cooling input during this interval."));
    const comparable=this.reviewCheckbox(form,this.t("Am verificat ventilația, aporturile solare, ocuparea și căldura reziduală.","I reviewed ventilation, solar gains, occupancy and residual heat."));
    const output=this.node("div");
    this.reviewButton(entry,form,()=>({type:"irpat_efficiency/inertia_review",room_id:room.value,
      start:new Date(start.value).getTime()/1000,end:new Date(end.value).getTime()/1000,
      heat_off_confirmed:off.checked,comparable:comparable.checked}),output,r=>{
      if(r.status!=="observed"){output.textContent=this.t("Date insuficiente sau interval neconfirmat.","Insufficient data or unreviewed interval.");return;}
      const fmt=(v,u)=>Number.isFinite(v)?v.toFixed(3)+" "+u:"—";
      output.append(this.node("p",this.t("Scădere observată: ","Observed drop: ")+fmt(r.drop_c,"°C")),
        this.node("p",this.t("Rată de răcire: ","Cooling rate: ")+fmt(r.rate_c_per_h,"°C/h")),
        this.node("p",this.t("Indicator normalizat: ","Normalized indicator: ")+fmt(r.normalized_per_h,"1/h")));
    });
    detail.append(this.node("p",this.t("Interval natural de 2 ore–7 zile, aliniat la 5 minute, cu toate măsurătorile. Nu opri instalația pentru test; analiza nu măsoară direct izolația sau capacitatea termică.","Natural interval of 2 hours–7 days, aligned to 5 minutes, with complete measurements. Do not switch equipment off for this test; the analysis does not directly measure insulation or heat capacity."),"muted"),form);
    return detail;
  }

  modeHistory(entry) {
    const box=this.node("section",undefined,"card"),history=entry.mode_history||{};
    if(!Object.keys(history).length)return this.node("div");
    box.append(this.node("h2",this.t("Istoric regimuri raportate","Reported mode history")));
    const labels={heating:this.t("Încălzire","Heating"),cooling:this.t("Răcire","Cooling"),dhw:this.t("ACM","DHW"),standby:this.t("Așteptare","Standby"),defrost:this.t("Degivrare","Defrost"),off:this.t("Oprit","Off")};
    const name=m=>labels[m]||this.t("Necunoscut","Unknown");
    for(const s of entry.topology.sources||[]){
      const h=history[s.id];if(!h)continue;
      box.append(this.node("h3",s.name));
      if(h.save_failed||h.pending_count>0)box.append(this.node("p",this.t("Salvare neconfirmată; evenimente restante: ","Save not confirmed; pending events: ")+(h.pending_count||0),"status-warm"));
      for(const e of (h.recent||[]).slice().reverse()){
        box.append(this.node("p",new Date(e.observed_at*1000).toLocaleString()+" · "+name(e.previous_mode)+" → "+name(e.mode)));
      }
      if(!(h.recent||[]).length)box.append(this.node("p",this.t("Nu există observații salvate.","No saved observations."),"muted"));
    }
    box.append(this.node("small",this.t("Ultimele 20 de observații salvate pe sursă, nu dovada unui regim continuu. Ora afișată este ora observării.","Last 20 saved observations per source, not proof of continuous operation. Time shown is observation time."),"muted"));
    return box;
  }

  liveDiagnostics(entry) {
    const box=this.node("section",undefined,"card");
    box.append(this.node("h2",this.t("Monitorizare instantanee","Live diagnostics")));
    const live=entry.live_diagnostics||{};
    const fmt=(v,unit)=>v==null?"—":v.toFixed(2)+" "+unit;
    const labels={
      boundary_unconfirmed:this.t("Limitele măsurătorilor neconfirmate","Measurement boundary unconfirmed"),
      insufficient_data:this.t("Date insuficiente","Insufficient data"),
      not_heat_pump:this.t("Nu este pompă de căldură","Not a heat pump"),
      observed_signed_ratio:this.t("Raport instantaneu semnat, nu COP pe interval","Instantaneous signed ratio, not period COP"),
      review_risk:this.t("Verifică riscul de condens","Review condensation risk"),
      surface_above_margin:this.t("Suprafață măsurată peste marjă; nu garantează siguranța","Measured surface above margin; safety not guaranteed"),
      proxy_only:this.t("Numai indicator din temperatura apei","Water temperature proxy only"),
      unknown:this.t("Date insuficiente","Insufficient data")
    };
    for(const source of entry.topology.sources||[]){
      const s=live.sources?.[source.id];
      if(!s)continue;
      box.append(this.node("h3",source.name));
      const reported=entry.reported_modes?.[source.id];
      if(reported){
        const modes={heating:this.t("Încălzire","Heating"),cooling:this.t("Răcire","Cooling"),dhw:this.t("ACM","Domestic hot water"),standby:this.t("Așteptare","Standby"),defrost:this.t("Degivrare","Defrost"),off:this.t("Oprit","Off")};
        box.append(this.node("p",this.t("Regim raportat: ","Reported mode: ")+(modes[reported.mode]||this.t("Necunoscut","Unknown")),"muted"));
      }
      const grid=this.node("div",undefined,"grid diagnostic-grid");
      grid.append(this.card("ΔT",fmt(s.delta_t_c,"°C")),
        this.card(this.t("Putere termică măsurată","Measured thermal power"),fmt(s.thermal_measured_w,"W")),
        this.card(this.t("Putere termică calculată","Calculated thermal power"),fmt(s.thermal_calculated_w,"W")),
        this.card(this.t("Putere electrică","Electrical power"),fmt(s.electrical_w,"W")));
      if(source.source_type==="heat_pump")grid.append(this.card(this.t("Raport instantaneu semnat","Signed instantaneous ratio"),fmt(s.signed_power_ratio,"")));
      box.append(grid);
      if(source.source_type==="heat_pump")box.append(this.node("small",labels[s.cop_status]||s.cop_status,"muted"));
    }
    if(this.displayMode==="cooling"){
      box.append(this.node("h3",this.t("Monitorizare condens","Condensation monitoring")));
      for(const room of entry.topology.rooms||[]){
        const c=live.condensation?.[room.id];
        if(!c)continue;
        const line=this.node("div",undefined,"room");
        const details=this.node("div");
        details.append(this.node("strong",room.name),
          this.node("div",this.t("Punct de rouă: ","Dew point: ")+fmt(c.dew_point_c,"°C")),
          this.node("div",this.t("Marjă suprafață: ","Surface margin: ")+fmt(c.surface?.margin_c,"°C")),
          this.node("div",this.t("Marjă apă (indicator): ","Water margin (proxy): ")+fmt(c.supply_proxy?.margin_c,"°C")));
        line.append(details,this.node("span",labels[c.status]||c.status));
        box.append(line);
      }
      box.append(this.node("p",this.t("Evaluare orientativă. Protecția fizică independentă rămâne obligatorie.","Advisory assessment. Independent hardware protection is required."),"muted"));
    }
    return box;
  }

  defrostHistory(entry) {
    const history=entry.defrost||{};
    if(!Object.keys(history).length)return this.node("div");
    const box=this.node("section",undefined,"card");
    box.append(this.node("h2",this.t("Istoric degivrări","Defrost history")));
    for(const source of entry.topology.sources||[]){
      const h=history[source.id];
      if(!h)continue;
      box.append(this.node("h3",source.name));
      if(h.save_failed)box.append(this.node("p",this.t("Salvarea istoricului a eșuat.","History save failed."),"status-warm"));
      if(h.pending_count>0)box.append(this.node("p",this.t("Evenimente în așteptarea salvării: ","Events awaiting storage: ")+h.pending_count,"status-warm"));
      if(!h.recent.length)box.append(this.node("p",this.t("Niciun ciclu complet observat.","No complete cycle observed."),"muted"));
      for(const e of h.recent.slice().reverse()){
        const row=this.node("div",undefined,"room");
        row.append(this.node("span",new Date(e.start*1000).toLocaleString()),
          this.node("span",this.t("Durată ~","Duration ~")+(e.duration_s/60).toFixed(1)+" min · "+(e.electric_kwh==null?"—":e.electric_kwh.toFixed(3)+" kWh")+" · "+this.t("Scădere tur ","Supply drop ")+(e.observed_supply_drop_c==null?"—":e.observed_supply_drop_c.toFixed(1)+" °C")));
        box.append(row);
      }
    }
    box.append(this.node("small",this.t("Ultimele 20 de cicluri complete pentru fiecare sursă. Eșantionare la 30 s; valorile sunt estimări, iar ciclurile incomplete nu sunt numărate.","Last 20 complete cycles per source. Sampled every 30 s; values are estimates and incomplete cycles are not counted."),"muted"));
    return box;
  }

  energyHistory(entry) {
    const history=entry.energy_history||{};
    const box=this.node("section",undefined,"card");
    if(!Object.keys(history).length)return this.node("div");
    box.append(this.node("h2",this.t("Istoric consum electric","Electricity consumption history")));
    if(entry.energy_save_failed)box.append(this.node("p",this.t("Salvarea istoricului energetic a eșuat.","Energy history save failed."),"status-warm"));
    const names={daily:this.t("Astăzi","Today"),weekly:this.t("Săptămâna curentă","This week"),monthly:this.t("Luna curentă","This month"),annual:this.t("Anul curent","This year")};
    for(const source of entry.topology.sources||[]){
      const periods=history[source.id];
      if(!periods)continue;
      box.append(this.node("h3",source.name));
      if(periods.daily?.status==="shared_meter"){
        box.append(this.node("p",this.t("Contor comun mai multor surse: consumul individual nu poate fi atribuit.","Meter shared by multiple sources: individual consumption cannot be attributed."),"status-warm"));
        continue;
      }
      const grid=this.node("div",undefined,"grid");
      for(const key of Object.keys(names)){
        const row=periods[key];
        if(!row)continue;
        const value=row.electric_kwh==null?"—":row.electric_kwh.toFixed(2)+" kWh";
        const card=this.card(names[key],value);
        card.append(this.node("small",this.t("Acoperire: ","Coverage: ")+(row.coverage==null?"—":(100*row.coverage).toFixed(1)+"%"),"muted"));
        if(row.current_tariff_cost){
          const c=row.current_tariff_cost;
          card.append(this.node("small",this.t("Estimare la tariful actual: ","Estimate at current tariff: ")+c.amount.toFixed(2)+" "+c.currency,"muted"));
        }
        if(source.source_type==="heat_pump"){
          for(const mode of ["heating","cooling"]){
            const m=row.modes?.[mode];
            if(!m||!m.seconds)continue;
            const label=mode==="heating"?this.t("Încălzire","Heating"):this.t("Răcire","Cooling");
            const ratio=m.cop==null?"—":m.cop.toFixed(2);
            card.append(this.node("small",label+" · "+this.t("Raport parțial Q/E: ","Partial Q/E ratio: ")+ratio,"muted"),
              this.node("small",this.t("Energie termică estimată / electrică asociată: ","Estimated heat / matched electricity: ")+m.thermal_kwh.toFixed(2)+" / "+m.electric_kwh.toFixed(2)+" kWh","muted"),
              this.node("small",this.t("Acoperire din perioada calendaristică: ","Share of calendar period: ")+(100*m.coverage).toFixed(1)+"%","muted"));
          }
        }
        grid.append(card);
      }
      box.append(grid);
    }
    box.append(this.node("p",this.t("Doar consumul observat din contorul configurat. Golurile nu sunt estimate. Totalurile folosesc calendarul local și alocarea aproximativă la intervale de 5 minute; după schimbarea contorului se afișează segmentul curent. Raportul Q/E utilizează numai configurația de măsurare confirmată curentă. Raportul Q/E folosește numai intervalele asociate și căldura estimată din puterea termică. Exclude ACM, standby, tranzițiile și degivrarea raportată separat; nu reprezintă COP-ul integral al perioadei.","Only observed consumption from the configured meter. Gaps are not estimated. Totals use local calendar dates and approximate five-minute allocation; after meter replacement the current segment is shown. Q/E uses only the current confirmed measurement configuration. The Q/E ratio uses matched intervals and heat estimated from thermal power. DHW, standby, transitions and separately reported defrost are excluded; this is not the full-period COP."),"muted"));
    return box;
  }

  fuelEconomics(entry) {
    const history=entry.fuel_history||{}, econ=entry.economics||{}, sources=entry.topology.sources||[];
    const box=this.node("section",undefined,"card");
    if(!sources.some(s=>s.fuel||s.scenario_cop!=null)&&!(econ.comparisons||[]).length)return this.node("div");
    box.append(this.node("h2",this.t("Combustibil și cost termic","Fuel and heat cost")));
    if(entry.fuel_save_failed)box.append(this.node("p",this.t("Salvarea istoricului combustibilului a eșuat.","Fuel history save failed."),"status-warm"));
    const periods={daily:this.t("Astăzi","Today"),weekly:this.t("Săptămâna curentă","This week"),monthly:this.t("Luna curentă","This month"),annual:this.t("Anul curent","This year")};
    for(const s of sources){
      const modeled=econ.modeled?.[s.id], rows=history[s.id];
      if(!s.fuel&&!modeled)continue;
      box.append(this.node("h3",s.name));
      if(s.fuel)box.append(this.node("p",this.t("Tarif combustibil: ","Fuel tariff: ")+s.fuel.tariff+" "+s.fuel.currency+"/"+s.fuel.billing_unit+" · "+s.fuel.basis));
      if(modeled)box.append(this.node("p",this.t("Scenariu estimat: ","Estimated scenario: ")+modeled.amount.toFixed(3)+" "+modeled.currency+"/kWh "+this.t("termic util","useful heat")+(modeled.complete?"":" · "+this.t("electricitate auxiliară necuantificată","auxiliary electricity unknown"))));
      if(rows){
        if(rows.daily?.status==="shared_meter"){box.append(this.node("p",this.t("Contor comun: atribuirea consumului este blocată.","Shared meter: consumption attribution blocked."),"status-warm"));continue;}
        const grid=this.node("div",undefined,"grid");
        for(const [key,label] of Object.entries(periods)){
          const r=rows[key];if(!r)continue;
          const card=this.card(label,r.fuel_kwh==null?"—":r.fuel_kwh.toFixed(2)+" kWh "+this.t("intrare","input"));
          card.append(this.node("small",this.t("Acoperire: ","Coverage: ")+(r.coverage==null?"—":(100*r.coverage).toFixed(1)+"%"),"muted"));
          if(r.current_tariff_cost){const c=r.current_tariff_cost;card.append(this.node("small",c.quantity.toFixed(3)+" "+c.unit+" · "+c.amount.toFixed(2)+" "+c.currency+" ("+this.t("tarif actual","current tariff")+")","muted"));}
          grid.append(card);
        }
        box.append(grid);
      }
    }
    for(const r of econ.comparisons||[]){
      const hp=sources.find(s=>s.id===r.heat_pump_id),fuel=sources.find(s=>s.id===r.fuel_source_id);
      box.append(this.node("p",(hp?.name||"")+" / "+(fuel?.name||"")+" · "+this.t("COP de egalitate economică: ","Break-even COP: ")+r.break_even_cop.toFixed(2)));
    }
    for(const z of entry.topology.zones||[]){
      if(z.source_strategy)box.append(this.node("small",z.name+" · "+this.t("Strategie declarată: ","Declared strategy: ")+z.source_strategy+(z.declared_switch_c==null?"":" · "+z.declared_switch_c+" °C"),"muted"));
    }
    box.append(this.node("p",this.t("Costurile combustibilului și electricității sunt separate, nu totaluri de factură. Scenariile nu reprezintă măsurători ale randamentului. COP-ul de egalitate nu este temperatura de comutare; integrarea nu comandă sursele.","Fuel and electricity costs are separate, not bill totals. Scenarios are not efficiency measurements. Break-even COP is not a switching temperature; the integration does not control sources."),"muted"));
    return box;
  }

  exportData(entry) {
    const box=this.node("details",undefined,"card journal");
    box.append(this.node("summary",this.t("Export date","Export data")));
    box.append(this.node("p",this.t("Fișierele includ date private despre instalație. Exportul JSON este o arhivă de analiză, nu un backup restaurabil. În CSV, energia asociată este un subset al consumului total; nu aduna aceste rânduri.","Files include private installation information. JSON is an analysis archive, not a restorable backup. Matched energy in CSV is a subset of total consumption; do not add these rows together."),"muted"));
    box.append(this.node("p",this.t("Backup restaurabil: deschide Settings → System → Backups în Home Assistant și include setările Home Assistant. Restaurarea poate înlocui și alte setări ale sistemului; efectueaz-o numai după verificarea conținutului și păstrarea unui backup actual.","Restorable backup: open Settings → System → Backups in Home Assistant and include Home Assistant settings. Restoration may replace other system settings; restore only after reviewing the contents and keeping a current backup."),"muted"));
    const select=this.node("select");
    for(const [value,ro,en] of [
      ["json","Arhivă JSON","JSON archive"],["temperatures","Temperaturi CSV","Temperatures CSV"],
      ["energy","Energie CSV","Energy CSV"],["fuel","Combustibil CSV","Fuel CSV"],["hydraulics","Debite CSV","Hydraulics CSV"],
      ["profiles","Profiluri CSV","Profiles CSV"],["observations","Observații CSV","Observations CSV"],
      ["comparisons","Comparații CSV","Comparisons CSV"],["defrost","Degivrări CSV","Defrost CSV"],
      ["modes","Regimuri CSV","Modes CSV"]
    ])select.append(new Option(this.t(ro,en),value));
    const label=this.node("label",this.t("Format și categorie","Format and category"));label.append(select);
    const button=this.node("button",this.t("Pregătește exportul","Prepare export"));button.type="button";
    const status=this.node("p","");status.setAttribute("role","status");
    const result=this.node("div");
    box.append(label,button,status,result);
    const clear=()=>{
      for(const link of result.querySelectorAll("a[data-export-url]")){
        URL.revokeObjectURL(link.href);this.exportUrls.delete(link.href);
      }
      result.replaceChildren();status.textContent="";
    };
    select.addEventListener("change",clear);
    button.addEventListener("click",async()=>{
      if(!this._hass||this.busy||this.journalSaving)return;
      clear();this.journalSaving=true;button.disabled=true;select.disabled=true;
      try{
        const selection=select.value;
        const file=await this._hass.callWS({type:"irpat_efficiency/export_data",entry_id:entry.entry_id,
          format:selection==="json"?"json":"csv",...(selection==="json"?{}:{section:selection})});
        if(!box.isConnected)return;
        const url=URL.createObjectURL(new Blob([file.content],{type:file.mime+";charset=utf-8"}));
        this.exportUrls.add(url);
        const link=this.node("a",this.t("Descarcă fișierul","Download file"),"action");
        link.href=url;link.download=file.filename;link.dataset.exportUrl="true";result.append(link);
        const warnings=Object.values(file.storage_status||{}).some(v=>v===true||(typeof v==="number"&&v>0));
        status.textContent=warnings?this.t("Export pregătit. Există salvări eșuate sau evenimente nesalvate excluse.","Export ready. Failed saves or excluded pending events exist."):this.t("Export pregătit.","Export ready.");
      }catch(error){
        if(box.isConnected)status.textContent=this.t("Exportul a eșuat. Dacă fișierul depășește 4 MiB, încearcă o categorie CSV.","Export failed. If the file exceeds 4 MiB, try a CSV category.")+" ("+String(error?.message||"")+")";
      }finally{this.journalSaving=false;button.disabled=false;select.disabled=false;}
    });
    return box;
  }

  clearExportUrls() {
    for(const url of this.exportUrls)URL.revokeObjectURL(url);
    this.exportUrls.clear();
  }

  buildingReports(entry) {
    const box=this.node("section",undefined,"card");
    box.append(this.node("h2",this.t("Rapoarte comparative ale clădirii","Building comparison reports")));
    const data=entry.building_reports||{};
    const observations=data.observations||[];
    const format=v=>Number.isFinite(v)?v.toFixed(2):"—";
    const when=v=>new Date(v*1000).toLocaleString();
    const input=(form,label,type,required=true)=>{
      const l=this.node("label",label), i=this.node("input");
      i.type=type;i.required=required;
      if(type==="number"){i.min="0";i.step="any";}
      if(type==="datetime-local")i.step="300";
      if(type==="text")i.maxLength=120;
      l.append(i);form.append(l);return i;
    };
    const check=(form,label)=>{
      const l=this.node("label"),i=this.node("input");
      i.type="checkbox";i.required=true;l.append(i,document.createTextNode(" "+label));form.append(l);return i;
    };
    const notes=form=>{
      const l=this.node("label",this.t("Observații","Notes")),i=this.node("textarea");
      i.maxLength=2000;l.append(i);form.append(l);return i;
    };
    const submit=(form,label,request)=>{
      const button=this.node("button",label);button.type="submit";
      const message=this.node("p","");message.setAttribute("role","status");form.append(button,message);
      form.addEventListener("submit",async ev=>{
        ev.preventDefault();
        if(this.journalSaving||this.busy||!this._hass)return;
        this.journalSaving=true;button.disabled=true;
        try{await this._hass.callWS({entry_id:entry.entry_id,...request()});}
        catch(error){
          message.textContent=this.t("Salvarea nu a fost confirmată. Verifică datele și lista înainte de reîncercare.","Save not confirmed. Check input and list before retrying.")+" ("+String(error?.message||"")+")";
          return;
        }finally{this.journalSaving=false;button.disabled=false;}
        await this.refresh();
      });
    };
    const seconds=i=>new Date(i.value).getTime()/1000;
    box.append(this.node("p",this.t("Perioade de 24 h–7 zile, cu date complete. Datele și orele sunt în fusul orar al browserului. Energia termică netă se introduce manual dintr-o măsurare verificată, inclusiv pierderile la degivrare; nu utiliza raportul Q/E parțial. Limita de măsurare trebuie să fie aceeași înainte și după.","Periods of 24 h–7 days with complete data. Dates and times use the browser time zone. Enter reviewed measured net heat manually, including defrost losses; do not use partial Q/E. Use the same measurement boundary before and after."),"muted"));
    for(const o of observations.slice().reverse()){
      const row=this.node("div",undefined,"journal-record");
      row.append(this.node("strong",o.name),this.node("small",when(o.start)+" — "+when(o.end)),
        this.node("small",this.t("Necesar aparent: ","Apparent heat input: ")+format(o.apparent_w_per_k)+" W/K · "+format(o.thermal_kwh)+" kWh"),
        this.node("small",this.t("Limită măsurare: ","Measurement boundary: ")+o.boundary_id));
      if(o.note)row.append(this.node("p",o.note));box.append(row);
    }
    const capture=this.node("details",undefined,"journal");
    capture.append(this.node("summary",this.t("Salvează perioada analizată","Save observed period")));
    const form=this.node("form");
    const name=input(form,this.t("Denumire","Name"),"text");
    const start=input(form,this.t("Început (multiplu de 5 minute)","Start (5-minute boundary)"),"datetime-local");
    const end=input(form,this.t("Sfârșit (multiplu de 5 minute)","End (5-minute boundary)"),"datetime-local");
    const boundary=input(form,this.t("Identificator limită de măsurare (același la ambele perioade)","Measurement boundary identifier (same for both periods)"),"text");
    const thermal=input(form,this.t("Energie termică netă măsurată (kWh)","Measured net thermal energy (kWh)"),"number");thermal.min="0.000001";
    const electric=input(form,this.t("Energie electrică (kWh, opțional)","Electricity (kWh, optional)"),"number",false);
    const note=notes(form);
    const reviewed=check(form,this.t("Confirm încălzirea, limita întregii clădiri, reprezentativitatea camerelor și energia netă pentru intervalul ales.","I confirm heating, whole-building boundary, representative rooms and net heat for this interval."));
    submit(form,this.t("Salvează observația","Save observation"),()=>({
      type:"irpat_efficiency/report_capture",name:name.value,start:seconds(start),end:seconds(end),
      boundary_id:boundary.value,thermal_kwh:Number(thermal.value),
      ...(electric.value!==""?{electric_kwh:Number(electric.value)}:{}),reviewed:reviewed.checked,note:note.value
    }));
    capture.append(form);box.append(capture);
    if(observations.length>=2){
      const detail=this.node("details",undefined,"journal");detail.append(this.node("summary",this.t("Compară înainte și după intervenție","Compare before and after intervention")));
      const form=this.node("form");
      const name=input(form,this.t("Denumire intervenție","Intervention name"),"text");
      const select=label=>{
        const l=this.node("label",label),s=this.node("select");s.required=true;
        s.append(new Option(this.t("Alege perioada","Choose period"),""));
        for(const o of observations)s.append(new Option(o.name+" · "+when(o.start),o.id));
        l.append(s);form.append(l);return s;
      };
      const before=select(this.t("Înainte","Before")),after=select(this.t("După","After"));
      const date=input(form,this.t("Moment intervenție","Intervention time"),"datetime-local");date.step="60";
      const note=notes(form);
      const comparable=check(form,this.t("Am verificat confortul, ventilația, aporturile, ocuparea și stocarea termică; perioadele sunt comparabile.","I reviewed comfort, ventilation, gains, occupancy and thermal storage; periods are comparable."));
      submit(form,this.t("Salvează comparația","Save comparison"),()=>({
        type:"irpat_efficiency/report_compare",name:name.value,before_id:before.value,after_id:after.value,
        intervention_at:seconds(date),comparable:comparable.checked,note:note.value
      }));
      detail.append(form);box.append(detail);
    }
    for(const r of (data.reports||[]).slice().reverse()){
      const row=this.node("div",undefined,"journal-record");
      row.append(this.node("strong",r.name+" · "+when(r.intervention_at)),
        this.node("small",r.before.name+" → "+r.after.name),
        this.node("small",format(r.before.apparent_w_per_k)+" → "+format(r.after.apparent_w_per_k)+" W/K"),
        this.node("strong",this.t("Variație normalizată observată: ","Observed normalized change: ")+format(r.normalized_change_pct)+"%"),
        this.node("small",this.t("Nu dovedește o economie cauzată de intervenție.","Does not prove savings caused by the intervention.")));
      if(r.note)row.append(this.node("p",r.note));box.append(row);
    }
    return box;
  }

  // Local vector icons, no network or emoji font dependency.
  icon(name) {
    const paths={home:"M3 10 12 3l9 7v10h-6v-7H9v7H3z",rooms:"M3 19V7m0 8h18m0 4V9h-9v6M3 11h5a3 3 0 0 1 3 3v1",sensor:"M10 14.5V5a2 2 0 0 1 4 0v9.5a4 4 0 1 1-4 0ZM12 8v8",loops:"M3 5h18M3 19h18M6 5v14M12 5v14M18 5v14",heat:"M12 3c1 5 6 6 6 12a6 6 0 0 1-12 0c0-3 2-5 3-6 0 4 3 4 3 4 2-3 0-7 0-10Z",check:"m5 12 4 4L19 6",weather:"M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10",target:"M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18m0 5a4 4 0 1 0 0 8 4 4 0 0 0 0-8",settings:"M4 7h16M4 17h16M8 4v6m8 4v6",up:"M12 20V4m-6 6 6-6 6 6",down:"M12 4v16m-6-6 6 6 6-6",clock:"M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18m0 4v5l3 2"};
    const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
    svg.setAttribute("viewBox","0 0 24 24");svg.setAttribute("width","24");svg.setAttribute("height","24");svg.setAttribute("fill","none");svg.setAttribute("stroke","currentColor");svg.setAttribute("stroke-width","1.7");svg.setAttribute("stroke-linecap","round");svg.setAttribute("stroke-linejoin","round");svg.setAttribute("aria-hidden","true");svg.classList.add("line-icon");
    const p=document.createElementNS("http://www.w3.org/2000/svg","path");p.setAttribute("d",paths[name]||paths.settings);svg.append(p);return svg;
  }

  async quickTargets(entry, roomIds, value) {
    if(this.busy||this.setupBusy||this.journalSaving)return;
    this.setupBusy=true;this.balanceMessage='';
    try {
      const current=entry.revision || (await this._hass.callWS({type:"irpat_efficiency/configuration",entry_id:entry.entry_id})).revision;
      await this._hass.callWS({type:"irpat_efficiency/configuration_action",entry_id:entry.entry_id,revision:current,action:"targets",payload:{mode:this.displayMode,room_ids:roomIds,value}});
      this.balanceMessage=this.t("Țintă salvată. Colectarea pentru recomandări reîncepe.","Target saved. Advice data collection starts again.");
    } catch(e) {this.balanceMessage=this.t("Nu s-a salvat. Actualizează și încearcă din nou.","Not saved. Refresh and try again.")+" "+String(e?.message||"");}
    finally {this.setupBusy=false;await this.refresh();}
  }

  balanceHeader(entry) {
    const t=entry.topology, mode=this.displayMode;
    const box=this.node("section",undefined,"balance-hero card");
    const readings=t.rooms.map(r=>entry.room_temperatures?.[r.id]?.[mode]);
    const known=readings.filter(v=>v?.temperature_c!=null&&v.valid_count===v.configured_count);
    const targets=known.filter(v=>v.target_c!=null);
    const within=targets.filter(v=>Math.abs(v.deviation_c)<=.3+1e-9).length;
    const heading=this.node("div",undefined,"hero-heading");heading.append(this.icon("home"),this.node("h2",this.t("Echilibrul casei","Home comfort")));box.append(heading);
    const stats=this.node("div",undefined,"comfort-grid");
    const metric=(icon,label,value,sub)=>{const e=this.node("div",undefined,"comfort-metric tone-"+icon);const title=this.node("div",undefined,"metric-title");title.append(this.icon(icon),this.node("small",label));e.append(title,this.node("strong",value),this.node("small",sub,"metric-sub"));return e;};
    const mean=known.length?known.reduce((a,v)=>a+v.temperature_c,0)/known.length:null;
    stats.append(metric("sensor",this.t("Interior","Inside"),mean==null?"—":mean.toFixed(1)+"°",known.length+"/"+t.rooms.length+" "+this.t("camere","rooms")),metric("target",this.t("În toleranță","On target"),within+"/"+targets.length,this.t("±0,3°C · citiri actuale","±0.3°C · current readings")));
    const out=entry.outdoor?.reading, hist=entry.outdoor?.history?.windows?.["24"];
    stats.append(metric("weather",this.t("Exterior","Outside"),out?.temperature_c==null?"—":out.temperature_c.toFixed(1)+"°",!out?this.t("Alege referința","Select a reference"):out.status==="reported"?out.name:this.t("Citire indisponibilă","Reading unavailable")));
    box.append(stats);
    if(out){box.append(this.node("small",this.t("Referință climatică: ","Weather reference: ")+out.entity_id+" · "+this.t("Media 24 h: ","24 h mean: ")+(hist?.mean_c==null?"—":hist.mean_c.toFixed(1)+" °C")+" · "+this.t("Acoperire: ","Coverage: ")+(hist?.coverage==null?"—":Math.round(hist.coverage*100)+"%"),"muted"));}
    const control=this.node("details",undefined,"room-detail");control.append(this.node("summary",this.t("Setează ținta pentru toate camerele","Set a target for all rooms")));
    if(t.rooms.length){
      const f=this.setupForm(control,this.t("Aplică tuturor camerelor","Apply to all rooms"),()=>this.quickTargets(entry,t.rooms.map(r=>r.id),Number(target.value)));
      f.form.classList.add("balance-form");
      const vals=t.rooms.map(r=>r[mode+"_target_c"]);
      const same=vals.every(v=>v!=null&&v===vals[0]);
      const target=this.setupField(f.form,this.t("Temperatură dorită (°C)","Desired temperature (°C)"),"number",same?vals[0]:22);target.min=5;target.max=40;target.step=.1;target.required=true;
      f.form.append(this.node("small",this.t("Schimbă doar țintele analizei, nu termostatele fizice.","Changes analysis targets only, not physical thermostats.")));f.finish();
    }else control.append(this.node("p",this.t("Importă mai întâi camerele.","Import rooms first.")));
    box.append(control);if(this.balanceMessage)box.append(this.node("p",this.balanceMessage));
    return box;
  }

  balancePanel(entry) {
    const box=this.node("section",undefined,"card advice-card");
    const head=this.node("div",undefined,"hero-heading");head.append(this.icon("target"),this.node("h2",this.t("Următorul pas","Next step")));box.append(head);
    if(this.displayMode!=="heating"){box.append(this.node("p",this.t("Recomandările direcționale sunt disponibile doar pentru încălzire. Răcirea necesită validări suplimentare.","Directional advice is available for heating only. Cooling requires additional validation.")));return box;}
    const rows=Object.entries(entry.balance_advice||{});
    if(!rows.length){box.append(this.node("p",this.t("Configurează distribuitorul, circuitele și sursa de încălzire pentru a începe analiza.","Configure the distributor, loops and heating source to start analysis.")));return box;}
    const labels={collecting:this.t("Colectăm 48 h de date după configurare.","Collecting 48 h of data after setup."),configure_operation:this.t("Confirmă tipul de încălzire și reglarea manuală a circuitelor în configurator.","Confirm heating operation and manual loop control in setup."),configure_rooms:this.t("Asociază toate circuitele, senzorii și țintele zonei (minimum două camere).","Link all zone loops, sensors and targets (at least two rooms)."),configure_outdoor:this.t("Alege o referință de temperatură exterioară.","Choose an outdoor temperature reference."),settling:this.t("Așteptăm 48 h după ultimul reglaj înregistrat.","Waiting 48 h after the last logged adjustment."),insufficient_data:this.t("Date insuficiente. Sunt necesare cel puțin 90% citiri comune în fiecare zi.","Insufficient data. At least 90% common readings per day are required."),weather_not_comparable:this.t("Condiții exterioare diferite sau sarcină termică prea mică. Nu recomandăm reglaje.","Different outdoor conditions or low heating demand. No adjustments advised.")};
    const names=new Map(entry.topology.rooms.map(r=>[r.id,r.name]));
    for(const [id,a] of rows){
      const zone=this.node("div",undefined,"advice-zone");zone.append(this.node("h3",a.name));
      if(a.last_adjustment_at!=null){
        zone.append(this.node("small",this.t("Ultima referință/reglaj: ","Last baseline/adjustment: ")+new Date(a.last_adjustment_at*1000).toLocaleString(),"muted"));
        if(a.remaining_hours>0){
          zone.append(this.node("p",this.t("Trecute: ","Elapsed: ")+a.elapsed_hours.toFixed(1)+" h · "+this.t("Rămase minimum: ","Minimum remaining: ")+a.remaining_hours.toFixed(1)+" h"));
          zone.append(this.node("small",this.t("Reevaluare cel mai devreme: ","Earliest reassessment: ")+new Date(a.earliest_review_at*1000).toLocaleString(),"muted"));
        }
      }
      if(a.status!=="review_conditions"){zone.append(this.node("p",labels[a.status]||a.status));box.append(zone);continue;}
      const key=entry.entry_id+":"+entry.revision+":"+id+":"+a.window_end+":"+JSON.stringify(a.rooms);
      zone.append(this.node("p",this.t("Analiză: 48 h · exterior ","Analysis: 48 h · outdoor ")+a.outdoor_means_c.map(v=>v.toFixed(1)+"°C").join(" / ")+" · "+Math.round(a.coverage*100)+"%"));
      if(a.curve_gate==="balance_required")zone.append(this.node("p",this.t("Meteoreglare blocată: echilibrează mai întâi toate încăperile alimentate de sursă.","Weather curve blocked: balance all rooms served by the source first."),"muted"));
      else if(a.curve_gate==="settling"||a.curve_gate==="balance_data_required")zone.append(this.node("p",this.t("Meteoreglare în așteptare: stabilizare sau date complete pentru toate zonele sursei.","Weather curve pending: settling or complete data for all source zones."),"muted"));
      if(!this.reviewedWindows.has(key)){
        const review=this.node("label",this.t("Confirm că în aceste 48 h a funcționat încălzirea normal, fără reglaje neînregistrate, ferestre deschise prelungit sau aporturi neobișnuite de căldură.","I confirm normal heating during these 48 h, without unlogged adjustments, prolonged open windows or unusual heat gains."));
        const cb=this.node("input");cb.type="checkbox";review.prepend(cb);zone.append(review);
        const b=this.setupButton(zone,this.t("Verifică recomandările","Review suggestions"),()=>{if(cb.checked){this.reviewedWindows.add(key);this.render();}});b.disabled=true;cb.addEventListener("change",()=>{b.disabled=!cb.checked;});
      }else{
        if(a.common_direction)zone.append(this.node("p",this.t("Echilibru relativ confirmat; abatere comună: analizează curba meteo sau temperatura de tur.","Relative balance confirmed; common error: review the weather curve or supply temperature."),"muted"));
        const desc={decrease:this.t("Verifică o mică reducere a debitului","Review a small flow reduction"),increase:this.t("Verifică o mică creștere a debitului","Review a small flow increase"),hold:this.t("Menține reglajul","Keep adjustment"),observe:this.t("Continuă monitorizarea","Continue monitoring")};
        for(const [rid,r] of Object.entries(a.rooms)){
          const line=this.node("div",undefined,"advice-line");line.append(this.icon(r.direction==="increase"?"up":r.direction==="decrease"?"down":r.direction==="hold"?"check":"clock"));
          const text=this.node("div");text.append(this.node("strong",names.get(rid)||rid),this.node("p",desc[r.direction]+" · "+(r.mean_error_c>0?"+":"")+r.mean_error_c.toFixed(2)+" °C"));
          const locations=r.circuits.map(c=>(entry.topology.manifolds.find(m=>m.id===c.manifold_id)?.name||"")+" #"+c.position);
          text.append(this.node("small",locations.join(" · "),"muted"));line.append(text);zone.append(line);
        }
        zone.append(this.node("small",this.t("Ipoteze, nu valori de debit calculate. Verifică limitele producătorului și debitul minim total; modifică gradual un singur reglaj, înregistrează înainte/după și așteaptă stabilizarea.","Hypotheses, not calculated flow values. Check manufacturer limits and minimum total flow; change one adjustment gradually, log before/after and wait for stabilization."),"muted"));
      }
      box.append(zone);
    }
    return box;
  }

  async openSetup(entry) {
    if (this.setupBusy || this.busy || this.journalSaving) return;
    this.setupBusy = true;
    this.setupError = '';
    this.setupMessage = '';
    try {
      this.setup = await this._hass.callWS({type:"irpat_efficiency/configuration",entry_id:entry.entry_id});
      this.setupEntry = entry.entry_id;
      this.setupStep = 0;
    } catch (e) {
      this.setupError = this.t("Configurarea nu a putut fi deschisă.","Could not open setup.")+" "+String(e?.message||"");
    } finally { this.setupBusy=false; this.render(); }
  }

  async setupAction(action,payload) {
    if(this.setupBusy || !this.setup) return;
    this.setupBusy=true; this.setupError=''; this.setupMessage='';
    const buttons=[...this.shadowRoot.querySelectorAll(".setup button")];
    buttons.forEach(b=>b.disabled=true);
    try {
      this.setup=await this._hass.callWS({type:"irpat_efficiency/configuration_action",
        entry_id:this.setupEntry,revision:this.setup.revision,action,payload});
      this.setupMessage=this.t("✓ Modificare salvată","✓ Change saved");
    } catch(e) {
      const messages={
        object_in_use:this.t("Elementul este încă folosit. Elimină mai întâi legăturile către senzori, circuite sau distribuitoare.","This item is still in use. Remove its sensor, circuit or distributor links first."),
        duplicate_entity:this.t("Acest senzor este deja folosit.","This sensor is already in use."),
        configuration_changed:this.t("Configurația s-a schimbat. Se încarcă datele actuale; repetă acțiunea.","Configuration changed. Reloading the latest data; repeat the action."),
        invalid_position:this.t("Verifică numărul sau poziția circuitului.","Check circuit count or position."),
        duplicate_position:this.t("Această poziție există deja.","This position already exists."),
        invalid_number:this.t("Verifică valorile numerice.","Check the numeric values."),
        invalid_name:this.t("Introdu un nume valid.","Enter a valid name."),
        invalid_entity:this.t("Entitate indisponibilă sau unitate incompatibilă.","Entity unavailable or incompatible unit."),
        invalid_fluid_properties:this.t("Verifică densitatea și căldura specifică.","Check density and specific heat."),
        invalid_mode_mapping:this.t("Verifică stările exacte ale senzorului.","Check exact sensor states."),
      };
      this.setupError=messages[e?.code]||this.t("Nu s-a putut salva: ","Could not save: ")+String(e?.message||e?.code||"");
      if(e?.code==="configuration_changed") {
        try { this.setup=await this._hass.callWS({type:"irpat_efficiency/configuration",entry_id:this.setupEntry}); } catch {}
      } else {
        // Keep the form and its values available for correction.
        buttons.forEach(b=>b.disabled=false);
        const msg=this.shadowRoot.querySelector(".setup-error");
        if(msg) msg.textContent=this.setupError;
        this.setupBusy=false;
        return;
      }
    }
    this.setupBusy=false; this.render();
  }

  setupField(form,label,type,value="",options=[]) {
    const wrap=this.node("label",label);
    const field=this.node(type==="select"?"select":"input");
    if(type==="select") for(const [id,name] of options){const o=this.node("option",name);o.value=id;field.append(o);}
    else {field.type=type; if(type==="number")field.step="any";}
    field.value=value??"";
    wrap.append(field);form.append(wrap);return field;
  }

  // Search is local, scoped to compatible entities; only the select is saved.
  entityField(form,label,value="",options=[]) {
    const group=this.node("div",undefined,"entity-picker");
    const top=this.node("div",undefined,"entity-picker-head");
    const caption=this.node("span",label);
    const field=this.node("select");
    const toggle=this.node("button",undefined,"entity-search-toggle secondary");
    toggle.type="button";toggle.setAttribute("aria-expanded","false");
    const glass=document.createElementNS("http://www.w3.org/2000/svg","svg");
    glass.setAttribute("viewBox","0 0 24 24");glass.setAttribute("width","16");glass.setAttribute("height","16");glass.setAttribute("fill","none");glass.setAttribute("stroke","currentColor");glass.setAttribute("stroke-width","2");glass.setAttribute("aria-hidden","true");
    const path=document.createElementNS("http://www.w3.org/2000/svg","path");path.setAttribute("d","M21 21l-6-6M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z");glass.append(path);
    toggle.append(glass,this.node("span",this.t("Caută ID","Search ID")));
    toggle.setAttribute("aria-label",this.t("Caută ID: ","Search ID: ")+label);
    field.setAttribute("aria-label",label);
    top.append(caption,toggle);group.append(top);
    const searchBox=this.node("div",undefined,"entity-search-box");searchBox.hidden=true;
    const search=this.node("input");search.type="search";search.placeholder=this.t("ID sau nume senzor…","Entity ID or name…");search.autocomplete="off";search.spellcheck=false;search.setAttribute("aria-label",this.t("Filtrează: ","Filter: ")+label);
    const count=this.node("small",undefined,"muted");count.setAttribute("aria-live","polite");
    const results=this.node("div",undefined,"entity-results");
    results.setAttribute("role","group");results.setAttribute("aria-label",this.t("Sugestii entități","Entity suggestions"));
    searchBox.append(search,count,results);group.append(searchBox,field);form.append(group);
    const all=new Map(options.map(([id,name])=>[id,name]));
    if(value&&!all.has(value))all.set(value,value);
    const normalize=v=>String(v??"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
    let limit=20;
    const choose=id=>{
      field.value=id;
      field.dispatchEvent(new Event("change",{bubbles:true}));
      search.value="";limit=20;searchBox.hidden=true;toggle.setAttribute("aria-expanded","false");
      refill(id);toggle.focus();
    };
    const refill=(selected)=>{
      const terms=normalize(search.value).trim().split(/\s+/).filter(Boolean);
      const matches=[...all].filter(([id,name])=>id&&terms.every(term=>normalize(id+" "+name).includes(term)));
      const query=normalize(search.value).trim();
      if(query)matches.sort((a,b)=>Number(normalize(b[0])===query)-Number(normalize(a[0])===query)||Number(normalize(b[0]).startsWith(query))-Number(normalize(a[0]).startsWith(query)));
      const ids=new Set(matches.map(([id])=>id));
      field.replaceChildren();
      for(const [id,name] of all){
        if(!id||id===selected||ids.has(id)){
          const o=this.node("option",name);o.value=id;field.append(o);
        }
      }
      field.value=selected;
      count.textContent=matches.length?matches.length+" "+this.t("rezultate","matches"):this.t("Niciun rezultat compatibil","No compatible matches");
      results.replaceChildren();
      if(searchBox.hidden)return;
      for(const [id,name] of matches.slice(0,limit)){
        const option=this.node("button",undefined,"entity-result");
        option.type="button";option.dataset.entityId=id;option.setAttribute("aria-pressed",String(id===selected));
        const displayName=String(name).replace(" ("+id+")","");
        option.append(this.node("strong",displayName),this.node("small",id,"entity-result-id"));
        option.addEventListener("click",()=>choose(id));results.append(option);
      }
      if(matches.length>limit){
        const more=this.node("button",this.t("Mai multe rezultate","Show more results"),"secondary entity-more");
        more.type="button";more.addEventListener("click",()=>{const old=limit;limit+=20;refill(field.value);results.querySelectorAll(".entity-result")[old]?.focus();});results.append(more);
      }
    };
    refill(value??"");
    toggle.addEventListener("click",()=>{
      searchBox.hidden=!searchBox.hidden;toggle.setAttribute("aria-expanded",String(!searchBox.hidden));
      limit=20;if(searchBox.hidden){search.value="";refill(field.value);}else {refill(field.value);search.focus();}
    });
    search.addEventListener("input",()=>{limit=20;refill(field.value);});
    search.addEventListener("keydown",e=>{
      if(e.key==="Enter"){e.preventDefault();const first=results.querySelector(".entity-result");if(first&&normalize(first.dataset.entityId)===normalize(search.value).trim())choose(first.dataset.entityId);else first?.focus();}
      else if(e.key==="ArrowDown"){e.preventDefault();results.querySelector(".entity-result")?.focus();}
      else if(e.key==="Escape"){e.preventDefault();search.value="";searchBox.hidden=true;toggle.setAttribute("aria-expanded","false");refill(field.value);toggle.focus();}
    });
    field.addEventListener("change",()=>{if(search.value){search.value="";refill(field.value);}});
    return field;
  }

  setupForm(parent,caption,action) {
    const form=this.node("form",undefined,"setup-form");
    const button=this.node("button",caption);button.type="submit";
    form.addEventListener("submit",e=>{e.preventDefault();action();});
    parent.append(form);
    return {form,finish:()=>form.append(button)};
  }

  setupButton(parent,label,action,secondary=false) {
    const button=this.node("button",label,secondary?"secondary":"");button.type="button";
    button.addEventListener("click",action);parent.append(button);return button;
  }

  setupRemove(parent,collection,id,name) {
    const details=this.node("details",undefined,"remove-confirm");
    details.append(this.node("summary",this.t("Elimină","Remove")));
    details.append(this.node("p",this.t("Elimini din THERMELYVO: ","Remove from THERMELYVO: ")+name));
    this.setupButton(details,this.t("Confirmă eliminarea","Confirm removal"),
      ()=>this.setupAction("remove",{collection,id,confirmed:true}),true);
    parent.append(details);
  }

  renderSetup(main) {
    const d=this.setup,t=d.topology;
    const box=this.node("section",undefined,"setup");
    main.append(box);
    const head=this.node("div",undefined,"setup-head");
    head.append(this.node("h2",this.t("Configurează casa","Set up your home")));
    this.setupButton(head,this.t("Înapoi la dashboard","Back to dashboard"),()=>{this.setup=null;this.setupMessage='';this.setupError='';this.refresh();},true);
    box.append(head,this.node("p",this.t("Fiecare modificare confirmată se salvează automat. Nu trimitem comenzi instalației.","Every confirmed change is saved automatically. No equipment commands are sent."),"muted"));
    const steps=[
      ["🏠",this.t("Casa","Home"),t.floors.length>0],
      ["🛏️",this.t("Camere","Rooms"),t.rooms.length>0],
      ["🌡️",this.t("Senzori","Sensors"),t.rooms.length>0&&t.rooms.every(r=>t.bindings.some(b=>b.room_id===r.id))],
      ["🔧",this.t("Circuite","Loops"),t.manifolds.length>0&&t.circuits.length>0&&t.circuits.every(c=>c.room_id)],
      ["♨️",this.t("Încălzire","Heating"),t.sources.length>0],
      ["✓",this.t("Verificare","Review"),false],
    ];
    const nav=this.node("nav",undefined,"setup-nav");
    steps.forEach(([icon,label,done],i)=>{
      const b=this.setupButton(nav,label,()=>{this.setupStep=i;this.setupError='';this.render();},true);
      b.replaceChildren(this.icon(["home","rooms","sensor","loops","heat","check"][i]),this.node("span",label),this.node("small",done?this.t("Configurat","Configured"):this.t("De verificat","Review")));
      b.setAttribute("aria-current",i===this.setupStep?"step":"false");b.dataset.complete=String(done);b.setAttribute("aria-label",(i+1)+". "+label+" · "+(done?this.t("Configurat","Configured"):this.t("De verificat","Review")));
    });
    box.append(nav);
    const status=this.node("p",this.setupMessage,"status-within");
    status.setAttribute("role","status");box.append(status);
    const error=this.node("p",this.setupError,"setup-error status-warm");error.setAttribute("role","alert");box.append(error);
    const section=this.node("section",undefined,"card");
    const blank=this.t("Alege…","Choose…");
    const choices=(items)=>items.map(x=>[x.id,x.name]);
    const num=(field)=>field.value===""?null:Number(field.value);
    const floorOptions=choices(t.floors),roomOptions=choices(t.rooms);
    const sensorOptions=(room, outdoor=false)=>{
      const area=t.rooms.find(r=>r.id===room)?.ha_area_id;
      const used=new Set([...t.bindings.map(b=>b.entity_id),...(t.telemetry||[]).map(b=>b.entity_id),t.outdoor_entity_id]);
      return d.entities.filter(e=>!used.has(e.entity_id)&&(outdoor?/^(sensor|weather)\./.test(e.entity_id):/^(sensor|climate)\./.test(e.entity_id)))
        .sort((a,b)=>Number(!!area&&b.area_id===area)-Number(!!area&&a.area_id===area)||a.name.localeCompare(b.name))
        .map(e=>[e.entity_id,(area&&e.area_id===area?"★ ":"")+e.name+" · "+(e.temperature_c==null?"—":e.temperature_c.toFixed(1)+" °C")+" ("+e.entity_id+")"]);
    };
    const stepHeading=this.node("div",undefined,"hero-heading");stepHeading.append(this.icon(["home","rooms","sensor","loops","heat","check"][this.setupStep]),this.node("h2",steps[this.setupStep][1]));section.append(stepHeading);
    if(this.setupStep===0) {
      section.append(this.node("p",this.t("Importă etajele și camerele existente sau adaugă etaje manual. Senzorii unici sau desemnați în Home Assistant sunt asociați automat.","Import existing floors and rooms or add floors manually. Unique or designated Home Assistant sensors are linked automatically.")));
      const areas=Object.entries(d.native_areas),nativeFloors=Object.entries(d.native_floors);
      if(areas.length){
        const f=this.setupForm(section,this.t("Importă camerele selectate","Import selected rooms"),()=>{
          const value=dest.value, selected=checks.filter(x=>x.checked).map(x=>x.value);
          const payload={area_ids:selected};
          if(value.startsWith("local:"))Object.assign(payload,{single_floor:true,fallback_floor:value.slice(6)});
          else if(value.startsWith("native:"))Object.assign(payload,{single_floor:true,single_native_floor:value.slice(7)});
          else if(value==="new")Object.assign(payload,{single_floor:true,fallback_name:newName.value});
          this.setupAction("import",payload);
        });
        const destinations=[...t.floors.map(x=>["local:"+x.id,x.name]),...nativeFloors.filter(([id])=>!t.floors.some(f=>f.ha_floor_id===id)).map(([id,name])=>["native:"+id,name]),["new",this.t("Un etaj nou","One new floor")],["native",this.t("Păstrează etajele din HA (omite camerele fără etaj)","Keep HA floors (skip rooms without a floor)")]];
        const dest=this.setupField(f.form,this.t("Pe ce etaj vrei să fie camerele?","Where should the rooms be placed?"),"select",destinations[0][0],destinations);
        const newName=this.setupField(f.form,this.t("Nume etaj nou pentru import","New import floor name"),"text",this.t("Parter","Ground floor"));newName.parentElement.hidden=dest.value!=="new";dest.addEventListener("change",()=>{newName.parentElement.hidden=dest.value!=="new";});
        const list=this.node("details",undefined,"import-list");list.open=true;list.append(this.node("summary",areas.length+" "+this.t("camere disponibile · selectează ce păstrezi","available rooms · choose what to keep")));
        const checks=areas.map(([id,a])=>{const label=this.node("label",a.name+(d.native_floors[a.floor_id]?" · "+d.native_floors[a.floor_id]:""));const cb=this.node("input");cb.type="checkbox";cb.value=id;cb.checked=true;label.prepend(cb);list.append(label);return cb;});
        f.form.append(list);f.finish();
      }
      if(t.floors.length>1){
        const merge=this.node("div",undefined,"setup-item");
        merge.append(this.node("h3",this.t("Elimină un etaj prin comasare","Remove a floor by merging")),
          this.node("p",this.t("Alege etajul de păstrat și etajul de eliminat. Camerele și distribuitoarele vor fi mutate; Home Assistant nu este modificat.","Choose the floor to keep and the floor to remove. Rooms and distributors move; Home Assistant is not changed.")));
        const mf=this.setupForm(merge,this.t("Confirmă comasarea","Confirm merge"),()=>this.setupAction("merge_floor",{id:remove.value,target_id:keep.value,confirmed:true}));
        const keep=this.setupField(mf.form,this.t("Etaj de păstrat","Floor to keep"),"select","",[["",blank],...floorOptions]);keep.required=true;
        const remove=this.setupField(mf.form,this.t("Etaj de eliminat","Floor to remove"),"select","",[["",blank]]);remove.required=true;
        keep.addEventListener("change",()=>{remove.replaceChildren();for(const [id,label] of [["",blank],...floorOptions.filter(x=>x[0]!==keep.value)]){const o=this.node("option",label);o.value=id;remove.append(o);}remove.value="";});
        mf.finish();section.append(merge);
      }
      for(const floor of t.floors){
        const row=this.node("details",undefined,"setup-item");row.append(this.node("summary",floor.name+" · "+t.rooms.filter(r=>r.floor_id===floor.id).length+" "+this.t("camere","rooms")));
        const f=this.setupForm(row,this.t("Aplică numele","Apply name"),()=>this.setupAction("rename",{collection:"floors",id:floor.id,name:name.value}));
        const name=this.setupField(f.form,this.t("Nume etaj","Floor name"),"text",floor.name);name.required=true;f.finish();
        row.append(this.node("small",t.rooms.filter(r=>r.floor_id===floor.id).length+" "+this.t("camere","rooms"),"muted"));
        if(t.floors.length>1){
          const merge=this.node("details",undefined,"remove-confirm");merge.append(this.node("summary",this.t("Combină cu alt etaj","Merge into another floor")));
          const mf=this.setupForm(merge,this.t("Mută camerele și elimină acest etaj","Move rooms and remove this floor"),()=>this.setupAction("merge_floor",{id:floor.id,target_id:to.value,confirmed:true}));
          const opts=floorOptions.filter(x=>x[0]!==floor.id);
          const to=this.setupField(mf.form,this.t("Etajul pe care îl păstrezi","Floor to keep"),"select",opts[0][0],opts);
          mf.form.append(this.node("small",this.t("Camerele și distribuitoarele sunt mutate; legăturile și istoricul arhivat rămân.","Rooms and distributors are moved; links and archived history are retained.")));mf.finish();row.append(merge);
        }
        this.setupRemove(row,"floors",floor.id,floor.name);section.append(row);
      }
      const f=this.setupForm(section,this.t("Adaugă etaj","Add floor"),()=>this.setupAction("add_floor",{name:name.value}));
      const name=this.setupField(f.form,this.t("Nume etaj nou","New floor name"),"text");name.required=true;f.finish();
    }
    if(this.setupStep===1){
      section.append(this.node("p",this.t("Adaugă camere și stabilește temperaturile dorite. Suprafața este opțională.","Add rooms and set desired temperatures. Floor area is optional.")));
      for(const room of t.rooms){
        const row=this.node("details",undefined,"setup-item");
        const temp=d.room_temperatures[room.id]?.heating?.temperature_c;
        row.append(this.node("summary","🛏️ "+room.name+" · "+(temp==null?"—":temp.toFixed(1)+" °C")));
        const f=this.setupForm(row,this.t("Aplică modificările","Apply changes"),()=>this.setupAction("edit_room",{id:room.id,name:name.value,area_m2:num(area),heating_target_c:num(heat),cooling_target_c:num(cool)}));
        const name=this.setupField(f.form,this.t("Nume","Name"),"text",room.name);name.required=true;
        const area=this.setupField(f.form,this.t("Suprafață (m²)","Area (m²)"),"number",room.area_m2);
        const heat=this.setupField(f.form,this.t("Temperatură dorită iarna (°C)","Desired winter temperature (°C)"),"number",room.heating_target_c);
        const cool=this.setupField(f.form,this.t("Temperatură dorită vara (°C)","Desired summer temperature (°C)"),"number",room.cooling_target_c);
        f.finish();
        if(t.floors.length>1){const mf=this.setupForm(row,this.t("Mută camera","Move room"),()=>this.setupAction("move_room",{id:room.id,floor_id:floor.value}));const floor=this.setupField(mf.form,this.t("Etaj","Floor"),"select",room.floor_id,floorOptions);mf.finish();}
        this.setupRemove(row,"rooms",room.id,room.name);section.append(row);
      }
      if(t.floors.length){
        const f=this.setupForm(section,this.t("Adaugă cameră","Add room"),()=>this.setupAction("add_room",{name:name.value,floor_id:floor.value}));
        const name=this.setupField(f.form,this.t("Nume cameră nouă","New room name"),"text");name.required=true;
        const floor=this.setupField(f.form,this.t("Etaj","Floor"),"select",t.floors[0].id,floorOptions);f.finish();
      }else section.append(this.node("p",this.t("Adaugă mai întâi un etaj în pasul Casa.","Add a floor in the Home step first.")));
    }
    if(this.setupStep===2){
      section.append(this.node("p",this.t("Alege senzorul care măsoară temperatura reală. ★ indică un senzor din aceeași încăpere Home Assistant.","Choose the sensor measuring the actual temperature. ★ indicates a sensor in the same Home Assistant area.")));
      for(const room of t.rooms){
        const row=this.node("details",undefined,"setup-item sensor-item");
        const current=d.room_temperatures[room.id]?.heating?.temperature_c;
        const bindings=t.bindings.filter(b=>b.room_id===room.id);row.dataset.linked=String(bindings.length>0);row.append(this.node("summary",room.name+" · "+(current==null?"—":current.toFixed(1)+" °C")+" · "+bindings.length+" "+this.t("senzori","sensors")));
        if(!bindings.length)row.append(this.node("p",this.t("Niciun senzor asociat","No sensor linked"),"muted"));
        for(const binding of bindings){
          const reading=d.room_temperatures[room.id]?.readings?.find(x=>x.entity_id===binding.entity_id);
          row.append(this.node("p",binding.name+" · "+(reading?.temperature_c==null?this.t("Citire indisponibilă","Reading unavailable"):reading.temperature_c.toFixed(1)+" °C")));
          this.setupRemove(row,"bindings",binding.id,binding.name);
        }
        const f=this.setupForm(row,this.t("Asociază senzor","Link sensor"),()=>this.setupAction("bind",{room_id:room.id,entity_id:sel.value}));
        const sel=this.entityField(f.form,this.t("Senzor temperatură","Temperature sensor"),"",[["",blank],...sensorOptions(room.id)]);sel.required=true;f.finish();section.append(row);
      }
      const f=this.setupForm(section,this.t("Aplică senzorul exterior","Apply outdoor sensor"),()=>this.setupAction("outdoor",{entity_id:out.value||null}));
      const existing=d.entities.find(e=>e.entity_id===t.outdoor_entity_id);
      const out=this.entityField(f.form,this.t("Temperatură exterioară (opțional)","Outdoor temperature (optional)"),t.outdoor_entity_id||"",[["",this.t("Niciunul","None")],...(t.outdoor_entity_id?[[t.outdoor_entity_id,existing?.name||t.outdoor_entity_id]]:[]),...sensorOptions(null,true)]);f.finish();
    }
    if(this.setupStep===3){
      section.append(this.node("p",this.t("Distribuitorul este piesa din care pleacă țevile către camere. Alege camera pentru fiecare circuit; nu ghicim traseele.","The distributor is where the floor pipes branch to rooms. Choose the room for each loop; pipe routes are never guessed.")));
      for(const m of t.manifolds){
        const row=this.node("div",undefined,"setup-item");
        row.append(this.node("h3",m.name));
        const rename=this.setupForm(row,this.t("Aplică numele","Apply name"),()=>this.setupAction("rename",{collection:"manifolds",id:m.id,name:mn.value}));
        const mn=this.setupField(rename.form,this.t("Nume distribuitor","Distributor name"),"text",m.name);mn.required=true;rename.finish();
        const circuits=t.circuits.filter(c=>c.manifold_id===m.id).sort((a,b)=>a.position-b.position);
        const diagram=this.node("div",undefined,"loops setup-diagram");
        for(const c of circuits){
          const loop=this.node("div",undefined,"loop");loop.append(this.node("strong",String(c.position)),this.node("div",undefined,"meter"),this.node("div",undefined,"supply"),this.node("div",undefined,"pipe"),this.node("div",undefined,"return"),this.node("small",t.rooms.find(r=>r.id===c.room_id)?.name||this.t("Neasociat","Unassigned")));diagram.append(loop);
        }
        row.append(diagram);
        for(const c of circuits){
          const f=this.setupForm(row,this.t("Aplică asocierea","Apply mapping"),()=>this.setupAction("map_circuit",{id:c.id,room_id:sel.value||null}));
          f.form.classList.add("inline-form");const sel=this.setupField(f.form,this.t("Circuit ","Loop ")+c.position,"select",c.room_id||"",[["",this.t("Neasociat","Unassigned")],...roomOptions]);f.finish();
          this.setupRemove(row,"circuits",c.id,this.t("Circuit ","Loop ")+c.position);
        }
        row.append(this.node("small",this.t("Schimbarea camerei păstrează istoricul vechi separat.","Changing a room keeps the old history separate."),"muted"));
        const f=this.setupForm(row,this.t("Adaugă circuit","Add loop"),()=>this.setupAction("add_circuit",{manifold_id:m.id,position:Number(pos.value)}));
        const pos=this.setupField(f.form,this.t("Poziție circuit nou","New loop position"),"number",Math.max(0,...circuits.map(c=>c.position))+1);pos.required=true;pos.min=1;pos.step=1;f.finish();
        this.setupRemove(row,"manifolds",m.id,m.name);section.append(row);
      }
      if(t.floors.length){
        const f=this.setupForm(section,this.t("Creează distribuitorul și circuitele","Create distributor and loops"),()=>this.setupAction("add_manifold",{name:name.value,floor_id:floor.value,count:Number(count.value),zone_id:zone?.value||null,zone_name:this.t("Încălzire principală","Main heating")}));
        const name=this.setupField(f.form,this.t("Nume distribuitor nou","New distributor name"),"text");name.required=true;
        const floor=this.setupField(f.form,this.t("Etaj","Floor"),"select",t.floors[0].id,floorOptions);
        const count=this.setupField(f.form,this.t("Câte circuite are?","How many loops?"),"number",1);count.min=1;count.max=100;count.step=1;count.required=true;
        let zone=null;
        if(t.zones.length)zone=this.setupField(f.form,this.t("Sistem de încălzire","Heating system"),"select",t.zones[0].id,choices(t.zones));
        else f.form.append(this.node("small",this.t("Se creează automat un sistem de încălzire principal.","A main heating system will be created automatically.")));
        f.finish();
      }else section.append(this.node("p",this.t("Adaugă mai întâi un etaj.","Add a floor first.")));
    }
    if(this.setupStep===4){
      section.append(this.node("p",this.t("Ce echipament încălzește casa? Poți adăuga mai multe surse.","What equipment heats the home? You can add multiple sources.")));
      const types=[["heat_pump",this.t("Pompă de căldură","Heat pump")],["gas",this.t("Centrală pe gaz","Gas boiler")],["electric",this.t("Electric","Electric")],["biomass",this.t("Lemne / peleți","Wood / pellets")],["district",this.t("Termoficare","District heating")],["hybrid",this.t("Hibrid","Hybrid")],["other",this.t("Altă sursă","Other source")],["unintegrated",this.t("Fără integrare","Not integrated")]];
      for(const source of t.sources){
        const row=this.node("div",undefined,"setup-item");row.append(this.node("strong","♨️ "+source.name+" · "+(types.find(x=>x[0]===source.source_type)?.[1]||source.source_type)));
        const f=this.setupForm(row,this.t("Aplică numele","Apply name"),()=>this.setupAction("rename",{collection:"sources",id:source.id,name:name.value}));
        const name=this.setupField(f.form,this.t("Nume sursă","Source name"),"text",source.name);name.required=true;f.finish();
        const roles=[
          ["supply_temperature","Temperatură tur","Supply temperature"],["return_temperature","Temperatură retur","Return temperature"],
          ["flow","Debit","Flow"],["electrical_power","Putere electrică","Electrical power"],
          ["electrical_energy","Energie electrică","Electrical energy"],["thermal_power","Putere termică","Thermal power"],
          ["thermal_energy","Energie termică","Thermal energy"],["compressor","Compresor","Compressor"],
          ["defrost","Degivrare","Defrost"],["burner","Arzător","Burner"],["pump","Pompă de circulație","Circulation pump"],
          ["pressure","Presiune","Pressure"]];
        const entities=d.source_entities||[], bindings=(t.telemetry||[]).filter(b=>b.group==="sources"&&b.owner_id===source.id);
        const readings=(d.source_readings||[]).filter(b=>b.owner_id===source.id);
        const sensorBox=this.node("div",undefined,"setup-item");
        sensorBox.append(this.node("h3",this.t("Senzorii echipamentului","Equipment sensors")),
          this.node("small",this.t("Selectează entitățile existente; valorile sunt cele raportate la deschiderea formularului. Poți lăsa câmpurile necompletate.","Select existing entities; values are snapshots at form load. Fields can be left blank.")));
        const fields={};
        const sf=this.setupForm(sensorBox,this.t("Salvează senzorii","Save sensors"),()=>this.setupAction("source_bindings",{id:source.id,bindings:Object.fromEntries(Object.entries(fields).map(([role,field])=>[role,field.value||null]))}));
        const isPump=source.source_type==="heat_pump";
        const tokens=source.name.toLowerCase().split(/[^a-z0-9]+/).filter(x=>x.length>=4);
        const score=e=>tokens.reduce((n,w)=>n+Number((e.name+" "+e.entity_id).toLowerCase().includes(w)),0);
        const optionsFor=role=>entities.filter(e=>e.roles.includes(role)).sort((a,b)=>score(b)-score(a)||a.name.localeCompare(b.name))
          .map(e=>[e.entity_id,(score(e)?"★ ":"")+e.name+" · "+(e.state??"—")+(e.unit?" "+e.unit:"")+" ("+e.entity_id+")"]);
        for(const [role,ro,en] of roles){
          const current=bindings.find(b=>b.role===role)?.entity_id||"";
          if(!current&&((isPump&&role==="burner")||(!isPump&&["compressor","defrost"].includes(role))))continue;
          const options=[["",this.t("Neasociat","Not linked")],...optionsFor(role)];
          if(current&&!options.some(x=>x[0]===current))options.push([current,current+" · "+this.t("Verifică entitatea","Review entity")]);
          fields[role]=this.entityField(sf.form,this.t(ro,en),current,options);
          const reading=readings.find(x=>x.role===role);
          if(current)sf.form.append(this.node("small",reading?.status==="reported"?String(reading.value)+(reading.unit?" "+reading.unit:""):this.t("Citire indisponibilă sau invalidă","Unavailable or invalid reading"),"muted"));
        }
        sf.finish();row.append(sensorBox);
        const props=this.node("details",undefined,"remove-confirm");props.append(this.node("summary",this.t("Agent termic și măsurători","Fluid and measurements")));
        const pf=this.setupForm(props,this.t("Salvează proprietățile","Save properties"),()=>this.setupAction("source_properties",{id:source.id,fluid_type:fluid.value,density_kg_m3:num(density),cp_j_kgk:num(cp),tariff:num(tariff),currency:currency.value||null,power_boundary_confirmed:power.checked,energy_boundary_confirmed:energy.checked}));
        const fluid=this.setupField(pf.form,this.t("Agent termic","Heat transfer fluid"),"select",source.fluid_type||"unknown",[["unknown",this.t("Necunoscut","Unknown")],["water",this.t("Apă","Water")],["propylene_glycol",this.t("Propilen glicol","Propylene glycol")],["ethylene_glycol",this.t("Etilen glicol","Ethylene glycol")],["other",this.t("Altul","Other")]]);
        const density=this.setupField(pf.form,this.t("Densitate (kg/m³)","Density (kg/m³)"),"number",source.density_kg_m3??"");
        const cp=this.setupField(pf.form,this.t("Căldură specifică (J/kg·K)","Specific heat (J/kg·K)"),"number",source.cp_j_kgk??"");
        const tariff=this.setupField(pf.form,this.t("Tarif electric / kWh","Electric tariff / kWh"),"number",source.tariff??"");
        const currency=this.setupField(pf.form,this.t("Monedă (RON, EUR)","Currency (RON, EUR)"),"text",source.currency||"");
        const check=(label,value)=>{const l=this.node("label",label),c=this.node("input");c.type="checkbox";c.checked=value===true;l.prepend(c);pf.form.append(l);return c;};
        const power=check(this.t("Confirm limitele măsurătorilor de putere","Confirm compatible power boundaries"),source.power_boundary_confirmed);
        const energy=check(this.t("Confirm limitele contoarelor de energie","Confirm compatible energy boundaries"),source.energy_boundary_confirmed);
        pf.form.append(this.node("small",this.t("Introdu densitatea și căldura specifică împreună, din datele agentului termic. Confirmă limitele numai dacă măsurătorile sunt compatibile.","Enter density and specific heat together from the fluid data. Confirm boundaries only for compatible measurements."),"muted"));pf.finish();row.append(props);
        const modes=this.node("details",undefined,"remove-confirm");modes.append(this.node("summary",this.t("Regim de funcționare raportat","Reported operating mode")));
        const modeFields={}, existing=source.mode_binding||{};
        const mof=this.setupForm(modes,this.t("Salvează regimurile","Save operating modes"),()=>this.setupAction("source_mode",{id:source.id,entity_id:modeSensor.value||null,states:Object.fromEntries(Object.entries(modeFields).map(([k,v])=>[k,v.value]))}));
        const modeOptions=[["",this.t("Neasociat","Not linked")],...entities.filter(e=>e.entity_id.startsWith("sensor.")).sort((a,b)=>score(b)-score(a)||a.name.localeCompare(b.name)).map(e=>[e.entity_id,e.name+" · "+(e.state??"—")])];
        if(existing.entity_id&&!modeOptions.some(x=>x[0]===existing.entity_id))modeOptions.push([existing.entity_id,existing.entity_id]);
        const modeSensor=this.entityField(mof.form,this.t("Senzor regim","Mode sensor"),existing.entity_id||"",modeOptions);
        for(const [k,ro,en] of [["heating","Încălzire","Heating"],["cooling","Răcire","Cooling"],["dhw","ACM","Domestic hot water"],["standby","Așteptare","Standby"],["defrost","Degivrare","Defrost"],["off","Oprit","Off"]]){
          modeFields[k]=this.setupField(mof.form,this.t(ro,en),"text",Object.keys(existing.mapping||{}).find(raw=>existing.mapping[raw]===k)||"");
        }
        mof.form.append(this.node("small",this.t("Introdu exact stările raportate de senzor; nu sunt comenzi.","Enter exact reported sensor states; these are not commands."),"muted"));mof.finish();row.append(modes);
        this.setupRemove(row,"sources",source.id,source.name);section.append(row);
      }
      for(const zone of t.zones){
        const row=this.node("div",undefined,"setup-item");row.append(this.node("h3",zone.name));
        const zf=this.setupForm(row,this.t("Confirmă modul de lucru","Confirm operating setup"),()=>this.setupAction("zone_settings",{id:zone.id,operating_mode:op.value,circuit_control:cc.value}));
        const op=this.setupField(zf.form,this.t("Cum este reglată temperatura apei?","How is water temperature controlled?"),"select",zone.operating_mode,[["unknown",this.t("Nu știu","Not sure")],["weather",this.t("Automat după vreme","Weather compensation")],["fixed",this.t("Temperatură fixă","Fixed temperature")],["onoff",this.t("Pornit/oprit după termostat","Thermostat on/off")]]);
        const cc=this.setupField(zf.form,this.t("Cum sunt reglate circuitele?","How are the loops controlled?"),"select",zone.circuit_control,[["unknown",this.t("Nu știu","Not sure")],["manual",this.t("Manual, de la debitmetre","Manual flow meters")],["open",this.t("Permanent deschise","Always open")],["automatic",this.t("Automat, cu actuatoare","Automatic actuators")]]);
        zf.form.append(this.node("small",this.t("Recomandările sunt disponibile doar cu tur fix sau compensat meteo și circuite manuale/deschise.","Advice requires fixed or weather-compensated supply and manual/open loops.")));zf.finish();section.append(row);
      }
      const f=this.setupForm(section,this.t("Adaugă sursă","Add source"),()=>this.setupAction("add_source",{name:name.value,source_type:kind.value,zone_ids:zones.filter(x=>x.checked).map(x=>x.value)}));
      const name=this.setupField(f.form,this.t("Nume sursă nouă","New source name"),"text");name.required=true;
      const kind=this.setupField(f.form,this.t("Tip echipament","Equipment type"),"select","heat_pump",types);
      const zones=t.zones.map(z=>{const label=this.node("label",z.name);const input=this.node("input");input.type="checkbox";input.value=z.id;input.checked=t.zones.length===1;label.prepend(input);f.form.append(label);return input;});
      f.finish();
    }
    if(this.setupStep===5){
      section.append(this.node("p",this.t("Poți încheia configurarea chiar dacă nu ai toți senzorii sau circuitele. Analizele care au nevoie de date lipsă rămân indisponibile.","You can finish without every sensor or loop. Analyses that require missing data remain unavailable.")));
      for(const [icon,label,done] of steps.slice(0,5))section.append(this.node("p",icon+" "+label+" — "+(done?this.t("Configurat","Configured"):this.t("De verificat","Review needed"))));
      this.setupButton(section,this.t("Finalizează","Finish"),()=>{this.setup=null;this.setupError='';this.setupMessage='';this.refresh();});
    }
    box.append(section);
    const foot=this.node("div",undefined,"setup-head");
    if(this.setupStep>0)this.setupButton(foot,this.t("← Anterior","← Previous"),()=>{this.setupStep--;this.render();},true);
    if(this.setupStep<5)this.setupButton(foot,this.t("Continuă →","Continue →"),()=>{this.setupStep++;this.render();});
    box.append(foot);
    const advanced=this.node("a",this.t("Setări avansate / Expert în Home Assistant","Advanced / Expert settings in Home Assistant"),"action");advanced.href="/config/integrations";box.append(advanced);
  }

  render() {
    this.clearExportUrls();
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
      .journal label:has(input[type="checkbox"]){display:flex;align-items:flex-start;gap:8px}.journal input[type="checkbox"]{width:18px;height:18px;flex:0 0 18px;accent-color:var(--primary-color)}.journal summary{cursor:pointer;padding:8px 0;overflow-wrap:anywhere}select:focus-visible,input:focus-visible,textarea:focus-visible,summary:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}.mode{flex-wrap:wrap}.room>div{min-width:0}.loop small{display:block;overflow-wrap:anywhere}
      .setup{max-width:760px;margin:16px auto}.setup-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}.setup-head h2{flex:1}.setup-nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:8px;margin:12px 0}.setup button{min-height:48px;white-space:normal;overflow-wrap:anywhere}.setup .secondary{background:var(--secondary-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color)}.setup-nav button[aria-current=step]{border:2px solid var(--primary-color);font-weight:bold}.setup-form{display:grid;gap:10px;margin:12px 0}.setup-form label{display:grid;gap:5px;font-size:1rem;overflow-wrap:anywhere}.setup-form input,.setup-form select{min-width:0;width:100%;box-sizing:border-box;min-height:46px;padding:8px;font:inherit;color:var(--primary-text-color);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:8px}.setup-form input[type=checkbox]{width:24px;min-height:24px}.setup-item{padding:14px 0;border-top:1px solid var(--divider-color);overflow-wrap:anywhere}.setup-item summary,.remove-confirm summary{cursor:pointer;padding:10px 0;min-height:24px}.remove-confirm{margin:8px 0}.setup-error:empty{display:none}.setup-diagram{max-width:100%}.setup .action{display:inline-block;margin-top:16px}
      :host{--ir-accent:var(--primary-color,#4f70db);--ir-surface:color-mix(in srgb,var(--card-background-color,#fff) 88%,transparent);--ir-edge:color-mix(in srgb,var(--primary-text-color,#222) 10%,transparent)}
      main{background:radial-gradient(ellipse at top right,color-mix(in srgb,var(--ir-accent) 10%,transparent),transparent 42%);min-height:100vh}
      .card{background:var(--ir-surface);border:1px solid var(--ir-edge);border-radius:20px;box-shadow:0 4px 20px #00000008;backdrop-filter:blur(12px)}
      button,a.action{border-radius:12px;font-weight:600;min-height:44px;transition:filter .15s}button:hover{filter:brightness(.95)}
      .line-icon{flex:none;color:var(--ir-accent)}.hero-heading{display:flex;align-items:center;gap:10px}.hero-heading h2{margin:8px 0}
      .comfort-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(115px,1fr));gap:10px;margin:14px 0}.comfort-metric{min-width:0;display:grid;gap:6px;border:1px solid var(--ir-edge);border-radius:16px;padding:12px;background:color-mix(in srgb,var(--ir-accent) 6%,transparent);overflow-wrap:anywhere}.comfort-metric strong{font-size:1.9rem;line-height:1.1;font-variant-numeric:tabular-nums}.comfort-metric small{color:var(--secondary-text-color)}
      .room-tile{border:1px solid var(--ir-edge);border-radius:16px;padding:12px;margin:10px 0;background:color-mix(in srgb,var(--card-background-color) 80%,var(--ir-accent) 3%)}.room-tile .room{border:0;padding:0}.room-tile .temperature strong{font-size:1.6rem}.room-detail{margin:10px 0 0}.room-detail summary{cursor:pointer;color:var(--ir-accent);font-weight:600;padding:8px 0}.advice-zone{border-top:1px solid var(--ir-edge);padding:12px 0}.advice-zone label{display:flex;align-items:flex-start;gap:10px;margin:10px 0}.advice-zone input[type=checkbox]{flex:none;width:22px;height:22px;accent-color:var(--ir-accent)}.advice-line{display:flex;align-items:flex-start;gap:12px;padding:12px 0;border-top:1px solid var(--ir-edge)}.advice-line p{margin:5px 0}
      .setup-nav button{display:grid;justify-items:center;gap:5px;padding:12px 6px;border-radius:16px;min-height:92px}.setup-nav small{font-size:.72rem;font-weight:400;color:var(--secondary-text-color)}.setup-nav button[aria-current=step]{background:color-mix(in srgb,var(--ir-accent) 12%,var(--card-background-color));box-shadow:0 3px 12px #0000000a}.setup-item{border:1px solid var(--ir-edge);border-radius:16px;padding:14px;margin:12px 0}.setup-form label[hidden]{display:none}.setup-form input,.setup-form select{border-radius:12px;border:1px solid var(--ir-edge);background:color-mix(in srgb,var(--card-background-color) 90%,var(--ir-accent) 5%)}.import-list label{display:flex;align-items:center;gap:10px;padding:7px 0}.import-list input[type=checkbox]{width:22px;height:22px;flex:none;accent-color:var(--ir-accent)}
      /* Dense dashboard: metrics are read-only, controls retain touch targets. */
      :host{font-size:14px;line-height:1.4}
      main{padding:12px}
      header{gap:8px}
      h1{font-size:1.3rem}h2{font-size:1.05rem;margin:8px 0}h3{font-size:.95rem;margin:8px 0 5px}h4{margin:8px 0 4px}
      p{margin:6px 0}
      .grid{gap:6px;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));margin:6px 0}
      .card{padding:10px;margin-bottom:8px;border-radius:12px;box-shadow:none;backdrop-filter:none;min-width:0}
      .grid>.card{margin:0}
      .metric{padding:7px 9px;overflow-wrap:anywhere}
      .metric>.muted{font-size:.79rem;line-height:1.25}
      .metric strong{font-size:1.2rem;line-height:1.2;margin-top:3px;font-variant-numeric:tabular-nums}
      .topology-grid{grid-template-columns:repeat(6,minmax(0,1fr));gap:5px}
      .topology-grid .metric{display:flex;align-items:center;justify-content:space-between;gap:4px}
      .topology-grid .metric strong{margin:0;font-size:1.12rem}
      .diagnostic-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:0;margin:4px 0}
      .diagnostic-grid>.metric{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 0;border:0;border-bottom:1px solid var(--ir-edge);border-radius:0;background:none}
      .diagnostic-grid>.metric:last-child{border-bottom:0}
      .diagnostic-grid .metric strong{margin:0;font-size:1rem;text-align:right;white-space:nowrap}
      .diagnostic-grid .metric>.muted{font-size:.85rem}
      .comfort-grid{gap:6px;margin:8px 0;grid-template-columns:repeat(auto-fit,minmax(100px,1fr))}
      .comfort-metric{padding:7px;gap:3px;border-radius:10px}
      .comfort-metric strong{font-size:1.35rem}
      .room-tile{padding:8px;margin:5px 0;border-radius:10px}
      .room-tile .temperature strong{font-size:1.25rem}
      .room{gap:6px;padding:5px 0}
      .room-detail{margin:4px 0 0}.room-detail summary{padding:5px 0}
      .history{margin:5px 0 7px;padding:6px;gap:4px}
      .mode{margin:8px 0;gap:5px}
      .advice-zone,.advice-line{padding:7px 0;gap:6px}
      .journal{margin:6px 0}.journal form{gap:7px;padding:6px 0}.journal-record{padding:6px 0}
      .journal input:not([type=checkbox]),.journal select,.journal textarea{padding:6px;min-height:44px}
      .flow-fields{gap:6px}
      .setup{margin:8px auto}.setup-head{margin:6px 0;gap:6px}
      .setup-nav{gap:5px;margin:6px 0;grid-template-columns:repeat(6,minmax(0,1fr))}
      .setup-nav button{padding:6px 3px;min-height:64px;border-radius:10px;gap:2px;font-size:.78rem}
      .setup-nav small{font-size:.66rem}
      .setup-item{padding:8px;margin:6px 0;border-radius:10px}
      .setup-form{gap:6px;margin:6px 0}.setup-form label{gap:3px;font-size:.9rem}
      .setup-form input,.setup-form select{min-height:44px;padding:6px}
      .setup-form input[type=checkbox]{min-height:24px}
      .setup button{min-height:44px}.setup-item summary,.remove-confirm summary{padding:6px 0}
      @media(max-width:720px){.topology-grid,.setup-nav{grid-template-columns:repeat(3,minmax(0,1fr))}}
      @media(max-width:600px){main{padding:8px}.room{flex-wrap:nowrap}.temperature{text-align:right}.journal button,.mode button{min-height:44px}.flow-fields{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:340px){.topology-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.room{flex-wrap:wrap}}

      /* dev3: compact rows and semantic color accents */
      :host{--ir-violet:#8b83e8;--ir-warm:#f09a50;--ir-cold:#55a9e9;--ir-good:#38b99a;--ir-accent:var(--ir-violet);font-size:14px;line-height:1.35}
      main{padding:8px;max-width:1180px;background:radial-gradient(ellipse at 100% 0,color-mix(in srgb,var(--ir-violet) 12%,transparent),transparent 44%)}
      header{gap:6px;margin-bottom:5px;flex-wrap:nowrap}.brand{display:flex;align-items:center;gap:6px;flex:1;min-width:0}.brand h1{font-size:1.05rem;line-height:1.2;flex:none}.brand .line-icon{width:20px;height:20px}.version-label{font-size:.66rem;color:var(--secondary-text-color);white-space:nowrap}
      header button,button,a.action{padding:7px 10px;min-height:44px;border-radius:9px;font-size:.85rem}
      .dashboard-controls{display:grid;gap:5px;margin:4px 0 7px}.setup-launch{width:fit-content;max-width:100%;background:color-mix(in srgb,var(--ir-violet) 19%,var(--card-background-color));color:var(--primary-text-color);border:1px solid color-mix(in srgb,var(--ir-violet) 45%,transparent)}
      .dashboard-toggles{display:flex;gap:6px;flex-wrap:wrap}.dashboard-toggles>.mode{flex:1;display:flex;flex-wrap:nowrap;margin:0;gap:3px;background:color-mix(in srgb,var(--primary-text-color) 5%,transparent);border:1px solid var(--ir-edge);border-radius:10px;padding:2px;min-width:0}
      .dashboard-toggles .mode button{flex:1;min-width:0;padding:5px 4px;white-space:nowrap;font-size:.78rem;background:transparent;color:var(--primary-text-color)}
      .dashboard-toggles .mode button[aria-pressed=true]{background:color-mix(in srgb,var(--ir-violet) 24%,var(--card-background-color));box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--ir-violet) 55%,transparent)}
      .thermal-mode button[aria-pressed=true]:first-child{background:color-mix(in srgb,var(--ir-warm) 22%,var(--card-background-color));box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--ir-warm) 50%,transparent)}
      .thermal-mode button[aria-pressed=true]:last-child{background:color-mix(in srgb,var(--ir-cold) 22%,var(--card-background-color));box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--ir-cold) 50%,transparent)}
      .installation-title{font-size:.83rem;margin:4px 2px;color:var(--secondary-text-color);font-weight:600}
      .card{padding:8px;margin-bottom:7px;border-radius:12px;background:var(--ir-surface)}
      .hero-heading{gap:6px}.hero-heading .line-icon{width:19px;height:19px}.hero-heading h2{margin:3px 0;font-size:1rem}
      .balance-hero{border-top:2px solid var(--ir-violet)}.comfort-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;margin:6px 0}
      .comfort-metric{--tone:var(--ir-violet);padding:6px;gap:3px;min-width:0;border:1px solid color-mix(in srgb,var(--tone) 30%,transparent);background:linear-gradient(135deg,color-mix(in srgb,var(--tone) 15%,transparent),color-mix(in srgb,var(--tone) 4%,transparent));border-radius:9px}
      .tone-sensor{--tone:var(--ir-warm)}.tone-target{--tone:var(--ir-good)}.tone-weather{--tone:var(--ir-cold)}
      .metric-title{display:flex;align-items:center;gap:3px;min-width:0}.metric-title .line-icon{color:var(--tone);width:15px;height:15px}.metric-title small{font-size:.75rem;font-weight:600;color:var(--primary-text-color)}
      .comfort-metric strong{font-size:1.35rem;line-height:1.15;color:var(--primary-text-color)}.metric-sub{font-size:.68rem;line-height:1.2;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
      .advice-card{border-left:3px solid var(--ir-violet)}.advice-card p{font-size:.86rem;margin:4px 0}.advice-zone{padding:5px 0}.advice-zone h3{margin:4px 0}.advice-line{padding:5px 0}.advice-line .line-icon{width:19px;height:19px}
      .room-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,285px),1fr));gap:5px;margin:5px 0}.room-tile{--tone:var(--ir-violet);padding:0;margin:0;border:1px solid color-mix(in srgb,var(--tone) 23%,var(--ir-edge));border-inline-start:3px solid var(--tone);border-radius:9px;background:color-mix(in srgb,var(--tone) 7%,var(--card-background-color));min-width:0}
      .room-tile[data-status=warm]{--tone:var(--ir-warm)}.room-tile[data-status=cold]{--tone:var(--ir-cold)}.room-tile[data-status=within]{--tone:var(--ir-good)}
      .room-tile .room-detail{margin:0}.room-tile .room-detail>summary{display:block;list-style:none;padding:7px;min-height:48px;box-sizing:border-box;color:var(--primary-text-color);font-weight:400}.room-tile summary::-webkit-details-marker{display:none}
      .room-tile .room{display:grid;grid-template-columns:19px minmax(0,1fr) auto;align-items:center;gap:6px;min-width:0}.room-tile .room>.line-icon{width:19px;height:19px;color:var(--tone)}.room-tile .label strong{font-size:.88rem}.room-tile .label small{display:block;font-size:.72rem;line-height:1.2}
      .room-tile .temperature strong{font-size:1.15rem;line-height:1.2;font-variant-numeric:tabular-nums}.room-tile .temperature small{font-size:.69rem;line-height:1.2}.room-tile .temperature{text-align:right}.room-tile .room-detail> :not(summary){margin:6px 8px}.room-tile .room-detail[open]>summary{border-bottom:1px solid var(--ir-edge)}
      .status-within{color:color-mix(in srgb,var(--ir-good) 72%,var(--primary-text-color))}.status-warm{color:color-mix(in srgb,var(--ir-warm) 72%,var(--primary-text-color))}.status-cold{color:color-mix(in srgb,var(--ir-cold) 72%,var(--primary-text-color))}
      .loops{padding:5px 2px;gap:5px}.loop{flex-basis:76px;font-size:.78rem}.meter{width:16px;height:34px;margin:3px auto}.supply,.return{height:5px}.pipe{height:9px}.loop small{font-size:.68rem}
      .setup{max-width:900px;margin:4px auto}.setup-nav{grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;margin:5px 0}.setup-nav button{display:flex;align-items:center;justify-content:center;gap:4px;min-height:44px;padding:5px 3px;position:relative}.setup-nav .line-icon{width:16px;height:16px}.setup-nav button small{display:none}.setup-nav button[data-complete=true]::after{content:"✓";color:var(--ir-good);font-size:.8rem}.setup-nav button[aria-current=step]{border:1px solid var(--ir-violet);background:color-mix(in srgb,var(--ir-violet) 17%,var(--card-background-color))}.setup-item{padding:6px 8px;margin:4px 0;border-radius:9px;background:color-mix(in srgb,var(--ir-violet) 4%,transparent)}.setup-item>summary{min-height:32px;box-sizing:border-box;font-weight:600;cursor:pointer}.sensor-item[data-linked=true]{border-inline-start:3px solid var(--ir-good)}.sensor-item[data-linked=false]{border-inline-start:3px solid var(--ir-warm)}
      .setup .setup-form{gap:5px;margin:5px 0}.setup .inline-form{grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:5px}.setup .inline-form button{max-width:124px}.setup .remove-confirm{margin:3px 0}.setup .remove-confirm summary{font-size:.78rem}.setup [role=status]:empty{display:none}
      @media(min-width:720px){.setup-nav{grid-template-columns:repeat(6,minmax(0,1fr))}.dashboard-controls{grid-template-columns:auto minmax(0,1fr);align-items:center}.dashboard-toggles{justify-self:end;width:min(100%,440px)}.room-grid{grid-template-columns:repeat(auto-fit,minmax(275px,1fr))}}
      @media(max-width:340px){.brand h1{font-size:.92rem}.brand .line-icon{display:none}.dashboard-toggles .mode button{font-size:.71rem}.comfort-metric strong{font-size:1.18rem}.room-tile .room{grid-template-columns:minmax(0,1fr) auto}.room-tile .room>.line-icon{display:none}}
      .entity-picker{display:grid;gap:4px;min-width:0}.entity-picker-head{display:flex;align-items:center;justify-content:space-between;gap:6px;font-size:.9rem}.entity-picker-head>span{min-width:0;overflow-wrap:anywhere}.setup .entity-search-toggle{display:inline-flex;align-items:center;gap:4px;padding:4px 7px;min-height:36px;font-size:.76rem;white-space:nowrap;color:var(--primary-text-color);background:color-mix(in srgb,var(--ir-violet) 14%,var(--card-background-color));border:1px solid color-mix(in srgb,var(--ir-violet) 40%,transparent)}.entity-search-box{display:grid;gap:3px}.entity-search-box[hidden]{display:none}.entity-search-box small{font-size:.72rem}.entity-picker select{max-width:100%}
      .entity-results{display:grid;gap:3px;max-height:245px;overflow-y:auto;overscroll-behavior:contain;min-width:0;padding:2px}.entity-results:empty{display:none}.setup .entity-result{display:grid;gap:2px;text-align:left;justify-items:start;min-height:44px;padding:6px 8px;min-width:0;width:100%;font-weight:400;background:color-mix(in srgb,var(--ir-violet) 7%,var(--card-background-color));color:var(--primary-text-color);border:1px solid var(--ir-edge);overflow-wrap:anywhere;white-space:normal}.entity-result strong{font-size:.82rem;line-height:1.25}.entity-result-id{font-family:monospace;font-size:.72rem;line-height:1.25;color:var(--secondary-text-color);overflow-wrap:anywhere}.setup .entity-result[aria-pressed=true]{border-color:var(--ir-violet);background:color-mix(in srgb,var(--ir-violet) 15%,var(--card-background-color))}.setup .entity-more{min-height:40px}
    `;
    root.append(style);
    const main = this.node("main");
    const header = this.node("header");
    const brand=this.node("div",undefined,"brand");brand.append(this.icon("home"),this.node("h1","THERMELYVO"),this.node("small","dev7","version-label"));header.append(brand);
    const refresh = this.node("button",this.t("Actualizează","Refresh"));
    refresh.disabled = this.busy || this.journalSaving;
    refresh.addEventListener("click",()=>this.refresh());
    header.append(refresh);
    main.append(header);
    if(this.setup){refresh.disabled=true;this.renderSetup(main);root.append(main);return;}
    if(this.setupError)main.append(this.node("p",this.setupError,"status-warm"));
    const controls=this.node("div",undefined,"dashboard-controls");main.append(controls);
    if(!this.entries.length){
      const link=this.node("a",this.t("Adaugă integrarea","Add integration"),"action");link.href="/config/integrations";main.append(link);
    }
    for(const entry of this.entries){
      const setup=this.node("button","⚙ "+this.t("Configurează casa","Set up home")+" · "+entry.name);
      setup.disabled=this.busy||this.setupBusy||this.journalSaving;
      setup.classList.add("setup-launch");setup.addEventListener("click",()=>this.openSetup(entry));controls.append(setup);
    }
    const modes = this.node("div",undefined,"mode");
    for (const [key,ro,en] of [["heating","Încălzire","Heating"],["cooling","Răcire","Cooling"]]) {
      const button=this.node("button",this.t(ro,en));
      button.setAttribute("aria-pressed",String(this.displayMode===key));
      button.disabled=this.busy||this.journalSaving;
      button.addEventListener("click",()=>{if(this.busy||this.journalSaving)return;this.displayMode=key;this.render();});
      modes.append(button);
    }
    modes.classList.add("thermal-mode");modes.setAttribute("aria-label",this.t("Regim afișat, fără comandă instalație","Display mode, no equipment control"));
    const view=this.node("div",undefined,"mode");
    view.setAttribute("role","group");view.setAttribute("aria-label",this.t("Nivelul interfeței","Interface level"));
    for(const [key,ro,en] of [["simple","Simplu","Simple"],["expert","Expert","Expert"]]){
      const button=this.node("button",this.t(ro,en));button.type="button";
      button.setAttribute("aria-pressed",String(this.viewMode===key));
      button.disabled=this.busy||this.journalSaving;
      button.addEventListener("click",()=>{if(this.busy||this.journalSaving)return;this.viewMode=key;this.render();});
      view.append(button);
    }
    const toggles=this.node("div",undefined,"dashboard-toggles");toggles.append(modes,view);controls.append(toggles);
    if (this.busy) main.append(this.node("p",this.t("Se încarcă…","Loading…")));
    if (this.error) main.append(this.node("p",this.t("Nu s-a putut încărca configurația. Încearcă din nou.","Could not load configuration. Try again.")));
    if (!this.busy && !this.error && !this.entries.length) main.append(this.node("p",this.t("Nu există o configurație activă.","No active configuration.")));
    for (const entry of this.entries) {
      const t = entry.topology;
      main.append(this.node("h2",entry.name,"installation-title"));
      if(entry.history_save_failed) main.append(this.node("p",this.t("Istoricul nu a putut fi salvat pe disc.","History could not be saved to disk."),"status-warm"));
      const period=this.node("select");
      period.setAttribute("aria-label",this.t("Interval istoric","History interval"));
      for(const h of ["24","48","72","168"]){const option=this.node("option",h+" h");option.value=h;period.append(option);}
      period.value=this.historyHours;
      period.disabled=this.busy||this.journalSaving;
      period.addEventListener("change",()=>{if(this.busy||this.journalSaving){period.value=this.historyHours;return;}this.historyHours=period.value;this.render();});
      const periodLabel=this.node("label",this.t("Interval statistic: ","Statistics interval: "));periodLabel.append(period);if(this.viewMode==="expert")main.append(periodLabel);
      const grid = this.node("div",undefined,"grid topology-grid");
      for (const [key,ro,en] of [["floors","Niveluri","Floors"],["rooms","Încăperi","Rooms"],["manifolds","Distribuitoare","Manifolds"],["circuits","Circuite","Circuits"],["zones","Zone","Zones"],["sources","Surse","Sources"]])
        grid.append(this.card(this.t(ro,en),(t[key]||[]).length));
      main.append(this.balanceHeader(entry),this.balancePanel(entry));
      if(this.viewMode==="expert")main.append(grid,this.liveDiagnostics(entry),this.energyHistory(entry),this.fuelEconomics(entry),this.thermalDiagnostics(entry));
      const rooms = new Map((t.rooms||[]).map(r=>[r.id,r]));
      for (const floor of t.floors||[]) {
        const section = this.node("section",undefined,"card");
        const floorTitle=this.node("div",undefined,"hero-heading");floorTitle.append(this.icon("rooms"),this.node("h2",floor.name));section.append(floorTitle);const roomGrid=this.node("div",undefined,"room-grid");section.append(roomGrid);
        for (const room of (t.rooms||[]).filter(r=>r.floor_id===floor.id)) {
          const roomCard=this.node("article",undefined,"room-tile");
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
            const age = reading.status==="future"?this.t(" · timestamp în viitor"," · future timestamp"):
              reading.status==="stale"?this.t(" · citire expirată"," · stale reading"):
              reading.age_seconds==null?"":this.t(" · raportat acum "," · reported ")+Math.floor(reading.age_seconds/60)+this.t(" min"," min ago");
            details.append(this.node("div",label+age,"muted"));
          }
          const right = this.node("div",undefined,"temperature");
          const partial = value?.valid_count>0 && value.valid_count<value.configured_count;
          const status = partial?"unknown":value?.status||"unknown";
          const labels = {within:this.t("În toleranță","Within tolerance"),warm:this.t("Peste țintă","Above target"),cold:this.t("Sub țintă","Below target"),unknown:this.t("Date insuficiente","Insufficient data")};
          const delta = value?.deviation_c;
          roomCard.dataset.status=status;
          left.append(this.node("small",(target==null?this.t("Țintă nesetată","No target"):this.t("Țintă ","Target ")+target.toFixed(1)+"°")+" · "+(value?.valid_count??0)+"/"+(value?.configured_count??0)+" "+this.t("senzori","sensors"),"muted"));
          right.append(this.node("strong",value?.temperature_c==null?"—":value.temperature_c.toFixed(1)+" °C","status-"+status),this.node("small",partial?this.t("Citiri parțiale","Partial readings"):labels[status]+(delta==null?"":" · "+(delta>0?"+":"")+delta.toFixed(1)+"°"),"status-"+status));
          row.append(this.icon("rooms"),left,right);
          const detail=this.node("details",undefined,"room-detail");const summary=this.node("summary");summary.append(row);detail.append(summary,details);summary.setAttribute("aria-label",room.name+" · "+this.t("Țintă și istoric","Target and history"));
          const tf=this.setupForm(detail,this.t("Aplică ținta","Apply target"),()=>this.quickTargets(entry,[room.id],Number(targetInput.value)));
          tf.form.classList.add("balance-form");
          const targetInput=this.setupField(tf.form,this.t("Temperatură dorită (°C)","Desired temperature (°C)"),"number",target??22);targetInput.min=5;targetInput.max=40;targetInput.step=.1;targetInput.required=true;tf.finish();
          const hist=entry.history?.[room.id];
          const stats=hist?.windows?.[this.historyHours];
          if(hist){
            const format=v=>v==null?"—":v.toFixed(1)+" °C";
            const prev=hist.yesterday_same_slot_c;
            const readings=sample?.readings||[];
            const fresh=readings.length>0&&readings.every(r=>r.status==="reported"&&r.temperature_c!=null);
            const historyBox=this.node("div",undefined,"history");
            const cells=[[this.t("Ieri, aceeași oră (5 min)","Yesterday, same time (5 min)"),format(prev)],
              [this.t("Diferență față de ieri","Difference from yesterday"),!fresh||prev==null||value?.temperature_c==null?"—":format(value.temperature_c-prev)],
              [this.t("Medie eșantioane","Sample mean"),format(stats?.mean_c)],
              [this.t("Min. / Max.","Min. / Max."),format(stats?.min_c)+" / "+format(stats?.max_c)],
              [this.t("Acoperire","Coverage"),stats?.coverage==null?"—":Math.round(stats.coverage*100)+"% ("+stats.count+"/"+stats.expected+")"]];
            for(const [caption,val] of cells){const cell=this.node("div");cell.append(this.node("small",caption,"muted"),this.node("strong",val));historyBox.append(cell);}
            detail.append(historyBox);
          }
          roomCard.append(detail);roomGrid.append(roomCard);
        }
        for (const manifold of (t.manifolds||[]).filter(m=>m.floor_id===floor.id)) {
          section.append(this.node("h3",manifold.name));
          const loops = this.node("div",undefined,"loops");
          const circuits = (t.circuits||[]).filter(c=>c.manifold_id===manifold.id).sort((a,b)=>a.position-b.position);
          for (const circuit of circuits) {
            const loop = this.node("div",undefined,"loop");
            const label = this.node("strong",String(circuit.position));
            const meter = this.node("div",undefined,"meter");
            const reading=this.recordedFlow(entry,manifold,circuit);
            const recorded=reading.value===null?this.t("Debit neînregistrat","Flow not recorded"):this.t("Debit manual înregistrat","Recorded manual flow");
            meter.setAttribute("aria-label",recorded);
            loop.append(label,meter,this.node("div",undefined,"supply"),this.node("div",undefined,"pipe"),this.node("div",undefined,"return"),this.node("div",circuit.name,"label"),this.node("small",rooms.get(circuit.room_id)?.name||this.t("Neasociat","Unassigned"),"muted"),this.node("div",reading.value===null?"— l/min":reading.value.toFixed(2)+" l/min","muted"),this.node("small",reading.timestamp?new Date(reading.timestamp).toLocaleString():"","muted"));
            loops.append(loop);
          }
          if (!circuits.length) section.append(this.node("p",this.t("Nu există circuite adăugate.","No circuits added."),"muted"));
          section.append(this.node("small",this.t("Ultima observație manuală din jurnal, nu debit live. Lipsa unei citiri este afișată cu —.","Latest manual journal observation, not live flow. Missing readings are shown as —."),"muted"),loops,this.journalForm(entry,manifold,circuits));
        }
        main.append(section);
      }
      if(this.viewMode==="expert")main.append(this.defrostHistory(entry),this.referenceProfiles(entry),this.weatherObservations(entry),this.inertiaReview(entry),this.modeHistory(entry),this.buildingReports(entry),this.exportData(entry));
    }
    main.append(this.node("p",this.t("Temperaturile sunt instantanee (media citirilor disponibile), cu toleranță provizorie ±0,3°C. Citirile expirate (peste 2 ore) sau cu timestamp în viitor sunt excluse. Istoricul local eșantionează la 5 minute, păstrează 8 zile și exclude rapoartele HA mai vechi de 2 ore; golurile rămân vizibile. Debitele se înregistrează manual în jurnal; nu sunt citiri live. Nu se transmit comenzi instalației.","Temperatures are snapshots (mean of available readings), with provisional ±0.3°C tolerance. Stale reports (over 2 hours old) and future timestamps are excluded. Local history samples every 5 minutes, retains 8 days and excludes HA reports older than 2 hours; gaps remain visible. Flows are recorded manually in the journal; they are not live readings. No commands are sent to equipment."),"muted"));
    root.append(main);
  }
}

if (!customElements.get("irpat-efficiency-panel")) customElements.define("irpat-efficiency-panel",IrpatEfficiencyPanel);
