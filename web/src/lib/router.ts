/** 极简 hash 路由：Phase 1 只有 Feed / 详情 / 关于三个视图，先不引入路由器依赖。 */

import { useEffect, useState } from "react";

export type Route =
  | { name: "feed" }
  | { name: "document"; id: number }
  | { name: "about" };

export function parseHash(hash: string): Route {
  const clean = hash.replace(/^#/, "");
  const match = /^\/d\/(\d+)$/.exec(clean);
  if (match) {
    return { name: "document", id: Number(match[1]) };
  }
  if (clean === "/about") {
    return { name: "about" };
  }
  return { name: "feed" };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() =>
    typeof window === "undefined" ? { name: "feed" } : parseHash(window.location.hash),
  );

  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}

export function documentHref(id: number): string {
  return `#/d/${id}`;
}
