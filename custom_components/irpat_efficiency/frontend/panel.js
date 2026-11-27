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
    this.exportUrls = new Set();
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
    this.clearExportUrls();
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
      if(!rows.length)box.append(this.node("p",this.t("Se colectează date sau zona nu poate fi analizată separat.","Collecting data or zone cannot be analyzed separately."),"muted"));
      for(const d of rows){
        const line=this.node("div",undefined,"room");
        const temp=v=>v==null?"—":v.toFixed(2)+" °C";
        line.append(this.node("span",new Date(d.start*1000).toLocaleString()+" — "+new Date(d.end*1000).toLocaleString()),
          this.node("span",this.t("Exterior ","Outdoor ")+temp(d.outdoor_c)+" · "+this.t("Abatere ","Error ")+temp(d.common_error_c)+" · "+Math.round(d.coverage*100)+"%"));
        box.append(line);
      }
    }
    box.append(this.node("small",this.t("Intervale sincronizate de 24 h pentru încălzire. Observațiile nu sunt încă validate ca fiind comparabile; nu se recomandă modificarea curbei.","Aligned 24 h heating windows. Observations are not yet reviewed for comparability; no curve adjustment is recommended."),"muted"));
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
      const grid=this.node("div",undefined,"grid");
      grid.append(this.card("ΔT",fmt(s.delta_t_c,"°C")),
        this.card(this.t("Putere termică măsurată","Measured thermal power"),fmt(s.thermal_measured_w,"W")),
        this.card(this.t("Putere termică calculată","Calculated thermal power"),fmt(s.thermal_calculated_w,"W")),
        this.card(this.t("Putere electrică","Electrical power"),fmt(s.electrical_w,"W")),
        this.card(this.t("Raport instantaneu semnat","Signed instantaneous ratio"),fmt(s.signed_power_ratio,"")));
      box.append(grid,this.node("small",labels[s.cop_status]||s.cop_status,"muted"));
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

  exportData(entry) {
    const box=this.node("details",undefined,"card journal");
    box.append(this.node("summary",this.t("Export date","Export data")));
    box.append(this.node("p",this.t("Fișierele includ date private despre instalație. Exportul JSON este o arhivă de analiză, nu un backup restaurabil. În CSV, energia asociată este un subset al consumului total; nu aduna aceste rânduri.","Files include private installation information. JSON is an analysis archive, not a restorable backup. Matched energy in CSV is a subset of total consumption; do not add these rows together."),"muted"));
    box.append(this.node("p",this.t("Backup restaurabil: deschide Settings → System → Backups în Home Assistant și include setările Home Assistant. Restaurarea poate înlocui și alte setări ale sistemului; efectueaz-o numai după verificarea conținutului și păstrarea unui backup actual.","Restorable backup: open Settings → System → Backups in Home Assistant and include Home Assistant settings. Restoration may replace other system settings; restore only after reviewing the contents and keeping a current backup."),"muted"));
    const select=this.node("select");
    for(const [value,ro,en] of [
      ["json","Arhivă JSON","JSON archive"],["temperatures","Temperaturi CSV","Temperatures CSV"],
      ["energy","Energie CSV","Energy CSV"],["hydraulics","Debite CSV","Hydraulics CSV"],
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
      main.append(grid,this.liveDiagnostics(entry),this.energyHistory(entry),this.defrostHistory(entry),this.thermalDiagnostics(entry),this.referenceProfiles(entry),this.weatherObservations(entry),this.buildingReports(entry),this.exportData(entry));
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
            const age = reading.status==="future"?this.t(" · timestamp în viitor"," · future timestamp"):
              reading.status==="stale"?this.t(" · citire expirată"," · stale reading"):
              reading.age_seconds==null?"":this.t(" · raportat acum "," · reported ")+Math.floor(reading.age_seconds/60)+this.t(" min"," min ago");
            details.append(this.node("div",label+age,"muted"));
          }
          left.append(details);
          const right = this.node("div",undefined,"temperature");
          const partial = value?.valid_count>0 && value.valid_count<value.configured_count;
          const status = partial?"unknown":value?.status||"unknown";
          const labels = {within:this.t("În toleranță","Within tolerance"),warm:this.t("Peste țintă","Above target"),cold:this.t("Sub țintă","Below target"),unknown:this.t("Date insuficiente","Insufficient data")};
          const delta = value?.deviation_c;
          right.append(this.node("strong",value?.temperature_c==null?"—":value.temperature_c.toFixed(1)+" °C","status-"+status),
            this.node("small",target==null?this.t("Țintă nesetată","No target"):this.t("Țintă ","Target ")+target.toFixed(1)+" °C"),
            this.node("small",partial?this.t("Citiri parțiale","Partial readings"):labels[status]+(delta==null?"":" · "+(delta>0?"+":"")+delta.toFixed(1)+" °C"),"status-"+status));
          row.append(left,right);
          section.append(row);
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
    main.append(this.node("p",this.t("Temperaturile sunt instantanee (media citirilor disponibile), cu toleranță provizorie ±0,3°C. Citirile expirate (peste 2 ore) sau cu timestamp în viitor sunt excluse. Istoricul local eșantionează la 5 minute, păstrează 8 zile și exclude rapoartele HA mai vechi de 2 ore; golurile rămân vizibile. Debitele se înregistrează manual în jurnal; nu sunt citiri live. Nu se transmit comenzi instalației.","Temperatures are snapshots (mean of available readings), with provisional ±0.3°C tolerance. Stale reports (over 2 hours old) and future timestamps are excluded. Local history samples every 5 minutes, retains 8 days and excludes HA reports older than 2 hours; gaps remain visible. Flows are recorded manually in the journal; they are not live readings. No commands are sent to equipment."),"muted"));
    root.append(main);
  }
}

if (!customElements.get("irpat-efficiency-panel")) customElements.define("irpat-efficiency-panel",IrpatEfficiencyPanel);
