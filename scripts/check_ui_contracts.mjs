// Static interface contracts. These do not substitute for HA runtime tests.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function checkContracts(source) {
  const checks=[];
  const check=(description,condition)=>{
    if(!condition) throw new Error(description);
    checks.push(description);
  };
  const same=(a,b)=>JSON.stringify([...a].sort())===JSON.stringify([...b].sort());
  const paths=(obj,base="")=>Object.entries(obj).flatMap(([k,v])=>
    v!==null&&typeof v==="object"?paths(v,base+k+"."):[base+k]);
  const base=JSON.parse(source["strings.json"]);
  const options=source["options_flow.py"];
  for(const lang of ["en","ro"]){
    const translation=JSON.parse(source["translations/"+lang+".json"]);
    check(lang+" translation paths match strings.json",same(paths(base),paths(translation)));
    const leaves=(obj)=>Object.values(obj).flatMap(v=>v!==null&&typeof v==="object"?leaves(v):[v]);
    check(lang+" translation text is nonempty",leaves(translation).every(v=>typeof v==="string"&&v.trim().length>0));
  }
  const methods=new Set([...options.matchAll(/async def async_step_(\w+)\(/g)].map(m=>m[1]));
  const menuLabels=Object.keys(base.options.step.init.menu_options);
  check("every translated menu action has a handler",menuLabels.every(name=>methods.has(name)));
  check("every non-save options step has a translation", [...methods].every(name=>name==="save"||Object.hasOwn(base.options.step,name)));
  const literalMenus=[...options.matchAll(/menu\.append\("(\w+)"\)/g)].map(m=>m[1]);
  const initialMenu=options.match(/menu\s*=\s*\[([^\]]+)\]/)?.[1]||"";
  const initialItems=[...initialMenu.matchAll(/"(\w+)"/g)].map(m=>m[1]);
  check("literal menu actions have labels", [...literalMenus,...initialItems].every(name=>menuLabels.includes(name)));
  for(const name of ["rooms","sources","manifolds"]){
    check("telemetry "+name+" menu and form exist",menuLabels.includes("telemetry_"+name)&&methods.has("telemetry_"+name));
  }
  const backend=source["panel.py"],frontend=source["frontend/panel.js"];
  const handlers=[...backend.matchAll(/@websocket_api\.websocket_command\(\{([\s\S]*?)\}\)\s*@websocket_api\.require_admin/g)]
    .map(m=>m[1].match(/f"\{DOMAIN\}\/([^"]+)"/)?.[1]).filter(Boolean);
  const declared=[...backend.matchAll(/f"\{DOMAIN\}\/([^"]+)"/g)].map(m=>m[1]);
  const used=[...new Set([...frontend.matchAll(/type:\s*"irpat_efficiency\/([^"]+)"/g)].map(m=>m[1]))];
  check("every backend command has the administrator decorator",same(handlers,declared));
  check("every frontend command maps to a backend command",used.every(name=>handlers.includes(name)));
  check("every backend command is registered",handlers.every(name=>backend.includes("websocket_api.async_register_command(hass, ws_"+name+")")));
  check("frontend does not issue direct HA service calls",!/\bcallService\s*\(|type:\s*["']call_service["']/.test(frontend));
  check("panel remains administrator-only",/require_admin\s*=\s*True/.test(backend));
  const manifest=JSON.parse(source["manifest.json"]);
  check("manifest domain matches panel namespace",manifest.domain==="irpat_efficiency");
  check("manifest includes panel runtime dependencies",["frontend","http","panel_custom","websocket_api"].every(d=>manifest.dependencies.includes(d)));
  return checks;
}

const base = new URL("../custom_components/irpat_efficiency/", import.meta.url);
const files = ["config_flow.py","options_flow.py","strings.json","translations/en.json","translations/ro.json","panel.py","frontend/panel.js","manifest.json"];
const source = Object.fromEntries(files.map(name => [name, readFileSync(fileURLToPath(new URL(name, base)), "utf8")]));
const checks = checkContracts(source);
for (const check of checks) console.log("PASS: " + check);
console.log(checks.length + " static interface contracts passed");
