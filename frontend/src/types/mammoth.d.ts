declare module "mammoth" {
  interface ConvertToHtmlResult {
    value: string;
    messages: unknown[];
  }

  interface MammothApi {
    convertToHtml(input: {
      arrayBuffer: ArrayBuffer;
    }): Promise<ConvertToHtmlResult>;
  }

  const mammoth: MammothApi;
  export default mammoth;
}
