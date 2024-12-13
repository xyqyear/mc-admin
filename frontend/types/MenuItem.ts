export default interface MenuItem {
  title: string;
  icon?: string;
  path?: string;
  items?: MenuItem[];
}
