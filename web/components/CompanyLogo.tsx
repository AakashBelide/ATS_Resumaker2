"use client";
// Company logo chip: real logo on a light rounded tile (so dark brand marks stay visible on
// our dark surfaces), with a lettered monogram fallback when the logo can't be fetched.
import { useState } from "react";

import { logoUrl, monogram } from "@/lib/logo";

export default function CompanyLogo({ name, size = 40 }: { name: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const url = logoUrl(name);
  const style = { width: size, height: size, fontSize: Math.round(size * 0.36) } as const;

  if (!url || failed) {
    return <span className="logo" data-fallback style={style}>{monogram(name)}</span>;
  }
  return (
    <span className="logo" style={style}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt="" onError={() => setFailed(true)} loading="lazy" />
    </span>
  );
}
