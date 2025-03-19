import axios from "axios";
import { defineStore } from "pinia";
import { getToken } from "@/utils/auth";

interface SysInfoResponse {
  status: "success" | "error";
  message: string;
  data: {
    cpu_percent: number;
    memory: {
      total: number;
      used: number;
      percent: number;
    };
    disk: {
      total: number;
      used: number;
      percent: number;
    };
    network: {
      upload: number;
      download: number;
    };
  };
}

export const useApiStore = defineStore("apiStore", () => {
  const get_sys_info = async (): Promise<SysInfoResponse> => {
    try {
      const apiUrl = import.meta.env.VITE_API_BASE_URL;
      const tokenInfo = getToken();

      if (!apiUrl) {
        throw new Error("API URL未配置，请检查环境变量VITE_API_BASE_URL");
      }

      if (!tokenInfo?.accessToken) {
        throw new Error("未登录或token已失效");
      }

      const response = await axios.get(`${apiUrl}/sys_info`, {
        headers: {
          Authorization: `Bearer ${tokenInfo.accessToken}`
        }
      });

      // 检查响应格式
      if (typeof response.data === "string") {
        console.error(
          "API响应格式错误，收到HTML而不是JSON:",
          response.data.substring(0, 100)
        );
        throw new Error("API响应格式错误");
      }

      console.log("API响应:", response.data);
      return response.data;
    } catch (error) {
      console.error("API请求失败:", error);
      throw error;
    }
  };

  return {
    get_sys_info
  };
});
