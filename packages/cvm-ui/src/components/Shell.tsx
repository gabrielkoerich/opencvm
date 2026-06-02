import { type ParentComponent } from "solid-js";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export const Shell: ParentComponent = (props) => (
  <div class="scanlines flex h-full w-full bg-bg text-text">
    <Sidebar />
    <div class="flex min-w-0 flex-1 flex-col">
      <TopBar />
      <main class="relative flex-1 overflow-auto">
        <div class="fade-in h-full">{props.children}</div>
      </main>
    </div>
  </div>
);
