// Run actual panel class with a minimal DOM stub. Not a browser rendering test.
import { readFileSync } from "node:fs";
function runPanelTests(source) {
  const registry=new Map();
  class Element { attachShadow(){} }
  const panel=new Function("HTMLElement","customElements",source+"\nreturn IrpatEfficiencyPanel;")(Element,{get:k=>registry.get(k),define:(k,v)=>registry.set(k,v)});
  const instance=new panel();
  const equal=(actual,expected,label)=>{if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error(label+": "+JSON.stringify(actual));return label;};
  const mid={id:"m"},cid={id:"c"},old="2026-11-26T12:00:00Z",latest="2026-11-27T12:00:00Z";
  const entry={journal:[{manifold_id:"m",timestamp:latest,flows_lmin:{c:0}},
      {manifold_id:"m",timestamp:old,flows_lmin:{c:1.4}},
      {manifold_id:"other",timestamp:"2026-11-27T13:00:00Z",flows_lmin:{c:8}}]};
  const checks=[
    equal(instance.viewMode,"simple","default simple interface"),
    equal(instance.recordedFlow(entry,mid,cid),{value:0,timestamp:latest},"zero flow is valid; sort and isolate manifold"),
    equal(instance.recordedFlow(entry,mid,{id:"unknown"}),{value:null,timestamp:latest},"missing flow is not zero"),
    equal(instance.recordedFlow({journal:[]},mid,cid),{value:null,timestamp:null},"empty journal"),
  ];
  entry.journal[0].flows_lmin={};
  checks.push(equal(instance.recordedFlow(entry,mid,cid),{value:null,timestamp:latest},"no mixing between observations"));
  entry.journal[0].flows_lmin={c:-1};
  checks.push(equal(instance.recordedFlow(entry,mid,cid),{value:null,timestamp:latest},"negative value excluded"));
  entry.journal[0].timestamp="invalid";
  checks.push(equal(instance.recordedFlow(entry,mid,cid),{value:1.4,timestamp:old},"invalid timestamp excluded"));
  return checks;
}
const source=readFileSync(new URL("../custom_components/irpat_efficiency/frontend/panel.js",import.meta.url),"utf8");
for(const result of runPanelTests(source))console.log("PASS: "+result);
