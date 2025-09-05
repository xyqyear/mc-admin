import { ReactNode } from "react";

export interface MenuItem {
  title: string;
  icon?: ReactNode;
  path?: string;
  items?: MenuItem[];
}
