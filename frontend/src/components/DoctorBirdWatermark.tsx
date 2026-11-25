"use client";

import React from "react";

/**
 * Custom vector silhouette of Jamaica's National Bird — the Red-Billed Streamertail ("Doctor Bird"),
 * modeled with its iconic hovering upright posture, fanned raised wing, slender bill, and twin sweeping tail streamers.
 */
export function DoctorBirdWatermark({
  className = "",
  variant = "backdrop",
}: {
  className?: string;
  variant?: "backdrop" | "emblem";
}) {
  const gradId = variant === "emblem" ? "jaBirdGradEmblem" : "jaBirdGradBackdrop";

  return (
    <svg
      viewBox="0 0 520 380"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={className}
    >
      <defs>
        <linearGradient id={gradId} x1="60" y1="60" x2="460" y2="340" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#22c55e" />
          <stop offset="52%" stopColor="#16a34a" />
          <stop offset="100%" stopColor="#e5b84b" />
        </linearGradient>
      </defs>

      {/* Slender straight bill pointing left */}
      <path
        d="M158 118 L86 112 C83 111.7 83 115.2 86 115.6 L157 125 Z"
        fill={variant === "emblem" ? "#e5b84b" : `url(#${gradId})`}
      />

      {/* Head, crest, chest & hovering body */}
      <path
        d="M156 117
           C164 103 184 97 204 104
           C218 109 229 120 242 132
           C258 148 274 176 289 205
           C294 214 297 222 292 228
           C279 235 256 232 238 220
           C217 206 203 184 195 162
           C188 144 178 134 166 129
           C160 126 155 122 156 117 Z"
        fill={`url(#${gradId})`}
      />

      {/* Raised, fanned hovering wing with feathered primary tips */}
      <path
        d="M236 136
           C272 104 328 62 396 34
           C406 30 412 34 405 42
           C392 54 374 66 358 76
           C378 68 398 60 414 54
           C422 52 425 58 416 64
           C396 76 372 88 350 98
           C369 92 387 86 401 82
           C408 81 409 87 401 92
           C378 105 352 117 328 127
           C345 123 360 119 372 117
           C378 116 379 122 371 127
           C346 141 317 154 290 166
           C276 172 263 175 254 170
           C244 164 234 148 236 136 Z"
        fill={`url(#${gradId})`}
      />

      {/* Short inner tail feathers */}
      <path
        d="M286 218 L344 260 C348 263 344 268 339 265 L278 228 Z"
        fill={`url(#${gradId})`}
      />

      {/* Upper sweeping streamer tail feather */}
      <path
        d="M280 223
           C296 234 301 244 288 248
           C264 254 222 249 180 256
           C164 259 156 263 160 266
           C165 269 179 266 196 263
           C232 257 272 261 296 254
           C312 249 310 233 289 218 Z"
        fill={`url(#${gradId})`}
      />

      {/* Lower iconic long curving streamer tail feather */}
      <path
        d="M287 222
           C318 256 340 288 334 314
           C327 339 286 346 226 355
           C194 360 168 367 152 371
           C146 372 144 368 151 365
           C174 356 212 349 250 343
           C296 335 320 326 324 308
           C328 288 308 260 278 226 Z"
        fill={`url(#${gradId})`}
      />
    </svg>
  );
}
