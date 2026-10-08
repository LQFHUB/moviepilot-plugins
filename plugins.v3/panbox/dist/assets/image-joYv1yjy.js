const n="/api/v1/system/img/false";function r(e){const t=String(e||"").trim();return t?/^https?:\/\//i.test(t)?`${n}?imgurl=${encodeURIComponent(t)}`:t:""}export{r as p};
